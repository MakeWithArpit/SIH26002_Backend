"""
AI-02 Condition-Aware ETA & Delay Estimation Service.
AI-02 Condition-Aware ETA & Delay Estimation Service (Vehicles facade).

Calculates base travel time from NER terrain road classification speeds,
then applies condition multipliers for dynamic disruption risk, heavy rainfall,
and real-time vehicle telemetry deficit.

Stable service wrapper that seamlessly allows dropping in Omji's trained
regression model in Phase 5 without API changes.
Delegates core calculation to apps.intelligence.services.eta.ETAEngine
while preserving the exact existing API and method signatures.
"""
import logging
from typing import List, Dict, Any, Optional

from apps.intelligence.services.eta.config import DEFAULT_ROAD_CLASS_SPEEDS
from apps.intelligence.services.eta.engine import ETAEngine

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
ROAD_CLASS_SPEEDS = DEFAULT_ROAD_CLASS_SPEEDS


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
        Preserves legacy return dictionary structure.
        """
        candidate_dict = {'segments': segments}
        eta_result = ETAEngine.estimate_eta(
            candidate=candidate_dict,
            rainfall_mm=rainfall_mm,
            weather_warning=weather_warning,
            current_vehicle_speed=current_vehicle_speed,
        )

        return {
            'base_eta_minutes': round(eta_result.base_eta_minutes, 1),
            'predicted_eta_minutes': round(eta_result.adjusted_eta_minutes, 1),
            'expected_delay_minutes': round(eta_result.expected_delay_minutes, 1),
            'delay_severity': eta_result.delay_severity,
            'top_factors': eta_result.top_factors,
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
        # Transition status to delayed if delay is substantial
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
