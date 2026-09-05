"""
Risk Prediction Service — Rule-based Geospatial Risk Engine.

Implements the AI-01 interface with explainable, weighted factor scoring:
- High landslide susceptibility zone: +30
- Historical landslide concentration: +15
- Moderate/High flood hazard zone: +15
- Heavy recent rainfall (> 50mm): +25
- IMD Weather warning: +10
- Recent field incident report (flood/landslide): +20

Score Range:
- 0 to 35: Low Risk
- 36 to 65: Medium Risk
- 66 to 100: High Risk / Disrupted
"""
import logging
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


class RiskPredictionService:
    """
    Stable service interface for segment disruption risk calculation.
    Swappable to ML model (Random Forest / XGBoost) in Phase 5 without
    changing controllers or schemas.
    """

    @classmethod
    def calculate_risk(cls, infra) -> dict:
        score = 0.0
        factors = []

        # 1. Landslide susceptibility
        if infra.landslide_susceptibility == 'high':
            score += 30.0
            factors.append('high landslide susceptibility')
        elif infra.landslide_susceptibility == 'medium':
            score += 15.0
            factors.append('moderate landslide susceptibility')

        # 2. Historical landslide concentration
        if infra.historical_landslide_count > 0:
            score += 15.0
            factors.append(f'historical landslide area ({infra.historical_landslide_count} recorded)')

        # 3. Flood hazard zone
        if infra.flood_hazard_zone in ('high', 'medium'):
            score += 15.0
            factors.append(f'{infra.flood_hazard_zone} flood hazard zone')

        # 4. Recent rainfall
        if infra.recent_rainfall_mm >= 50.0:
            score += 25.0
            factors.append(f'heavy rainfall ({infra.recent_rainfall_mm}mm)')
        elif infra.recent_rainfall_mm > 20.0:
            # Proportional contribution for moderate rain
            rain_contrib = round((infra.recent_rainfall_mm / 50.0) * 25.0, 1)
            score += rain_contrib
            factors.append(f'moderate rainfall ({infra.recent_rainfall_mm}mm)')

        # 5. Weather warning
        if infra.weather_warning:
            score += 10.0
            factors.append('active IMD weather warning')

        # 6. Recent field incident reports (last 24 hours)
        recent_threshold = timezone.now() - timedelta(hours=24)
        if hasattr(infra, 'incident_reports'):
            recent_reports = infra.incident_reports.filter(
                server_timestamp__gte=recent_threshold,
                incident_type__in=['flood', 'landslide', 'road_damage'],
            )
            if recent_reports.exists():
                score += 20.0
                factors.append('recent field incident report')

        # Physical condition modifier (poor or damaged road elevates risk)
        if infra.condition == 'damaged':
            score += 20.0
            factors.append('infrastructure physically damaged')
        elif infra.condition == 'poor':
            score += 10.0
            factors.append('poor infrastructure condition')

        # Clamp total score between 0.0 and 100.0
        risk_score = round(min(100.0, max(0.0, score)), 1)
        disruption_prob = round(risk_score / 100.0, 2)

        if risk_score >= 66.0:
            risk_level = 'high'
        elif risk_score >= 36.0:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return {
            'risk_score': risk_score,
            'disruption_probability': disruption_prob,
            'risk_level': risk_level,
            'top_factors': factors,
        }

    @classmethod
    def assess_and_update(cls, infra):
        """Calculate and persist updated disruption risk state to the infrastructure record."""
        assessment = cls.calculate_risk(infra)

        infra.risk_score = assessment['risk_score']
        infra.disruption_probability = assessment['disruption_probability']
        infra.risk_level = assessment['risk_level']
        infra.top_factors = assessment['top_factors']

        # Update operational status if severely disrupted
        if infra.risk_score >= 80.0 and infra.status == 'accessible':
            infra.status = 'risky'
        elif infra.risk_score < 36.0 and infra.status == 'risky':
            infra.status = 'accessible'

        infra.save(update_fields=[
            'risk_score',
            'disruption_probability',
            'risk_level',
            'top_factors',
            'status',
            'recent_rainfall_mm',
            'weather_warning',
            'last_assessed_at',
        ])
        return infra
