"""
Risk Factor Evaluators for Infrastructure Disruption Risk Engine.

Evaluates static geospatial enrichment and dynamic district-level weather data:
- Landslide Susceptibility (Static GSI)
- Historical Landslide Activity (Static GSI inventory)
- Recent 24-Hour Rainfall (Dynamic WeatherSnapshot)
- Flood Hazard (Inactive / pending authoritative data source)
- Official Weather Warning (Inactive / pending authoritative warning source)
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from apps.intelligence.services.risk.config import RiskConfig


@dataclass
class FactorAssessment:
    """
    Structured, explainable evaluation result for a single risk factor.
    """
    name: str
    value: Any
    contribution: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "contribution": round(self.contribution, 2),
            "reason": self.reason,
        }


class FactorEvaluator:
    """
    Evaluates individual risk factors against persisted Infrastructure & District data.
    """

    @classmethod
    def evaluate_landslide_susceptibility(
        cls, infra: Any, config: RiskConfig
    ) -> FactorAssessment:
        raw_val = getattr(infra, "landslide_susceptibility", None)
        norm_val = str(raw_val).strip().lower() if raw_val else ""

        if norm_val == "high":
            return FactorAssessment(
                name="landslide_susceptibility",
                value="high",
                contribution=config.weight_landslide_susceptibility_high,
                reason="High landslide susceptibility zone detected",
            )
        else:
            display_val = raw_val or "none"
            return FactorAssessment(
                name="landslide_susceptibility",
                value=display_val,
                contribution=0.0,
                reason=f"Landslide susceptibility is {display_val} (no high susceptibility penalty)",
            )

    @classmethod
    def evaluate_historical_landslides(
        cls, infra: Any, config: RiskConfig
    ) -> FactorAssessment:
        hist_count = getattr(infra, "historical_landslide_count", 0) or 0
        nearby_count = getattr(infra, "landslide_nearby_count", 0) or 0
        count = max(hist_count, nearby_count)

        if count > 0:
            return FactorAssessment(
                name="historical_landslide",
                value=count,
                contribution=config.weight_historical_landslide,
                reason=f"Historical landslide activity detected ({count} nearby incident(s))",
            )
        else:
            return FactorAssessment(
                name="historical_landslide",
                value=0,
                contribution=0.0,
                reason="No historical landslides recorded within proximity threshold",
            )

    @classmethod
    def evaluate_recent_rainfall(
        cls, infra: Any, config: RiskConfig
    ) -> FactorAssessment:
        """
        Evaluate 24-hour rainfall from the latest persisted district WeatherSnapshot.

        Formula:
        - rainfall <= min_threshold (20mm): 0.0
        - min_threshold < rainfall < max_threshold (50mm):
            proportional = ((rainfall - min) / (max - min)) * max_weight (25)
        - rainfall >= max_threshold (50mm): max_weight (25.0)

        If WeatherSnapshot is unavailable:
        - contribution = 0.0
        - value = None
        - explicit explanation (not assumed to be 0mm confirmed rainfall)
        """
        district = getattr(infra, "district", None)
        if district is None:
            return FactorAssessment(
                name="recent_rainfall",
                value=None,
                contribution=0.0,
                reason="Weather data unavailable: infrastructure segment has no associated district",
            )

        # Retrieve latest successful WeatherSnapshot for district
        latest_snapshot = None
        if hasattr(district, "weather_snapshots"):
            latest_snapshot = district.weather_snapshots.order_by("-recorded_at").first()
        elif hasattr(district, "latest_weather"):
            latest_snapshot = district.latest_weather

        if latest_snapshot is None:
            return FactorAssessment(
                name="recent_rainfall",
                value=None,
                contribution=0.0,
                reason="Weather data unavailable for district. No recent weather snapshot found.",
            )

        rainfall = float(latest_snapshot.rainfall_mm if latest_snapshot.rainfall_mm is not None else 0.0)

        min_thresh = config.rainfall_min_threshold_mm
        max_thresh = config.rainfall_max_threshold_mm
        max_weight = config.weight_heavy_rainfall

        if rainfall <= min_thresh:
            return FactorAssessment(
                name="recent_rainfall",
                value=rainfall,
                contribution=0.0,
                reason=f"24-hour rainfall ({rainfall:.1f} mm) is at or below the minimum threshold ({min_thresh:.1f} mm)",
            )
        elif rainfall >= max_thresh:
            return FactorAssessment(
                name="recent_rainfall",
                value=rainfall,
                contribution=max_weight,
                reason=f"24-hour rainfall ({rainfall:.1f} mm) is at or above the heavy-rainfall threshold ({max_thresh:.1f} mm)",
            )
        else:
            proportional = ((rainfall - min_thresh) / (max_thresh - min_thresh)) * max_weight
            contrib = round(proportional, 2)
            return FactorAssessment(
                name="recent_rainfall",
                value=rainfall,
                contribution=contrib,
                reason=f"24-hour rainfall ({rainfall:.1f} mm) is moderate (proportional contribution: {contrib:.1f}/{max_weight:.1f})",
            )

    @classmethod
    def evaluate_flood_hazard(
        cls, infra: Any, config: RiskConfig
    ) -> FactorAssessment:
        """
        Flood hazard data source is not yet integrated.
        Must remain inactive (0.0 points) without fabricating signals.
        """
        return FactorAssessment(
            name="flood_hazard",
            value=None,
            contribution=0.0,
            reason="Flood hazard data source is currently inactive/unavailable",
        )

    @classmethod
    def evaluate_weather_warning(
        cls, infra: Any, config: RiskConfig
    ) -> FactorAssessment:
        """
        Official government weather warning data source is not yet integrated.
        Must remain inactive (0.0 points) without fabricating signals.
        """
        return FactorAssessment(
            name="weather_warning",
            value=None,
            contribution=0.0,
            reason="Official weather warning data source is currently inactive/unavailable",
        )

    @classmethod
    def evaluate_all(
        cls, infra: Any, config: RiskConfig
    ) -> List[FactorAssessment]:
        """
        Evaluate all risk factors in standard order.
        """
        return [
            cls.evaluate_landslide_susceptibility(infra, config),
            cls.evaluate_historical_landslides(infra, config),
            cls.evaluate_recent_rainfall(infra, config),
            cls.evaluate_flood_hazard(infra, config),
            cls.evaluate_weather_warning(infra, config),
        ]
