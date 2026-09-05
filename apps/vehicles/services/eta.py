"""
AI-02 Condition-Aware ETA & Delay Estimation Service.

Calculates base travel time from NER terrain road classification speeds,
then applies condition multipliers for dynamic disruption risk, heavy rainfall,
and real-time vehicle telemetry deficit.

Stable service wrapper that seamlessly allows dropping in Omji's trained
regression model in Phase 5 without API changes.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Base speeds (km/h) for NER terrain classifications
ROAD_CLASS_SPEEDS = {
    'national_highway': 50.0,
    'state_highway': 40.0,
    'major_district_road': 30.0,
    'rural_road': 25.0,
    'bridge': 30.0,
    'tunnel': 40.0,
}


class ETAEstimationService:
    @classmethod
    def calculate_eta_for_route(
        cls,
        segments: List[Dict[str, Any]],
        current_vehicle_speed: Optional[float] = None,
        weather_warning: bool = False,
        rainfall_mm: float = 0.0,
    ) -> dict:
        """
        Calculate condition-aware ETA and expected delay.
        Segments can be list of dicts with:
        {'length_km': float, 'road_classification': str, 'risk_score': float, 'status': str}
        """
        total_base_time = 0.0
        total_predicted_time = 0.0
        delay_factors = []

        total_distance = sum(s.get('length_km', 0.0) for s in segments)

        for s in segments:
            length = s.get('length_km', 0.0)
            road_class = s.get('road_classification', 'national_highway')
            risk_score = s.get('risk_score', 0.0)
            status = s.get('status', 'accessible')

            base_speed = ROAD_CLASS_SPEEDS.get(road_class, 45.0)
            seg_base_time = (length / base_speed) * 60.0  # in minutes
            total_base_time += seg_base_time

            # 1. Road Risk Penalty
            # High risk segments require convoy speeds / cautionary driving
            if risk_score >= 66.0 or status == 'risky':
                # 40% to 75% extra travel time on high-risk sector
                risk_penalty_factor = 1.4 + ((risk_score - 66.0) / 100.0)
                seg_predicted_time = seg_base_time * risk_penalty_factor
                seg_delay = seg_predicted_time - seg_base_time
                if seg_delay > 2.0:
                    delay_factors.append(
                        f"Hazardous segment ({s.get('name', 'Road')}) slow speed (+{round(seg_delay, 1)} mins)"
                    )
            elif risk_score >= 36.0:
                # 15% extra travel time on medium-risk sector
                seg_predicted_time = seg_base_time * 1.15
                seg_delay = seg_predicted_time - seg_base_time
                if seg_delay > 2.0:
                    delay_factors.append(
                        f"Moderate terrain risk ({s.get('name', 'Road')}) (+{round(seg_delay, 1)} mins)"
                    )
            else:
                seg_predicted_time = seg_base_time

            # If segment is blocked, huge penalty
            if status == 'blocked':
                seg_predicted_time += 120.0
                delay_factors.append(f"Road blockage on {s.get('name', 'Segment')} (+120 mins)")

            total_predicted_time += seg_predicted_time

        # 2. Weather Penalty (along the corridor)
        weather_delay = 0.0
        if rainfall_mm >= 50.0:
            weather_delay = total_base_time * 0.25  # +25% delay
            delay_factors.append(f"Heavy rainfall delay ({rainfall_mm}mm, +{round(weather_delay, 1)} mins)")
        elif rainfall_mm > 20.0:
            weather_delay = total_base_time * 0.12  # +12% delay
            delay_factors.append(f"Moderate rain speed reduction (+{round(weather_delay, 1)} mins)")

        if weather_warning and weather_delay == 0.0:
            weather_delay = total_base_time * 0.10  # +10% for cautionary driving
            delay_factors.append(f"Active IMD advisory (+{round(weather_delay, 1)} mins)")

        total_predicted_time += weather_delay

        # 3. Real-time telemetry speed deficit adjustment
        # If current speed is significantly lower than average base speed, factor into remaining ETA
        if current_vehicle_speed is not None and current_vehicle_speed > 0:
            avg_base_speed = (total_distance / (total_base_time / 60.0)) if total_base_time > 0 else 45.0
            if current_vehicle_speed < (avg_base_speed * 0.6):  # Slowed by more than 40%
                telemetry_delay = (total_base_time * 0.15)
                total_predicted_time += telemetry_delay
                delay_factors.append(
                    f"Real-time vehicle slow moving traffic ({current_vehicle_speed} km/h, +{round(telemetry_delay, 1)} mins)"
                )

        expected_delay = max(0.0, total_predicted_time - total_base_time)

        # Delay severity classification
        if expected_delay >= 45.0:
            delay_severity = 'critical'
        elif expected_delay >= 20.0:
            delay_severity = 'moderate'
        elif expected_delay >= 5.0:
            delay_severity = 'minor'
        else:
            delay_severity = 'none'

        return {
            'base_eta_minutes': round(total_base_time, 1),
            'predicted_eta_minutes': round(total_predicted_time, 1),
            'expected_delay_minutes': round(expected_delay, 1),
            'delay_severity': delay_severity,
            'top_factors': delay_factors,
        }

    @classmethod
    def update_trip_eta(cls, trip, segments: Optional[List[Dict[str, Any]]] = None):
        """
        Calculates and updates ETA fields directly on a Trip instance.
        """
        # If segments not provided, construct fallback segment from origin/destination distance
        if not segments:
            # Approximate distance in km using PostGIS distance
            dist_m = trip.origin.distance(trip.destination) * 111000.0  # Approx meters
            dist_km = max(5.0, round(dist_m / 1000.0, 1))
            segments = [{
                'name': f"{trip.origin_name} to {trip.destination_name}",
                'length_km': dist_km,
                'road_classification': 'national_highway',
                'risk_score': 0.0,
                'status': 'accessible',
            }]

        current_speed = trip.vehicle.current_speed if trip.vehicle else None
        res = cls.calculate_eta_for_route(
            segments=segments,
            current_vehicle_speed=current_speed,
        )

        trip.base_eta_minutes = res['base_eta_minutes']
        trip.predicted_eta_minutes = res['predicted_eta_minutes']
        trip.expected_delay_minutes = res['expected_delay_minutes']
        trip.eta_factors = res['top_factors']

        # Transition status to delayed or at_risk if delay is substantial
        if res['expected_delay_minutes'] >= 30.0 and trip.status == 'on_route':
            trip.status = 'delayed'

        trip.save(update_fields=[
            'base_eta_minutes',
            'predicted_eta_minutes',
            'expected_delay_minutes',
            'eta_factors',
            'status',
            'last_eta_updated_at',
        ])
        return trip
