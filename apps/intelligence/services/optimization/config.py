"""
Centralized Configuration for Route Optimization Engine.
"""
from dataclasses import dataclass
from django.conf import settings

DEFAULT_OPTIMIZATION_DISTANCE_WEIGHT = 0.60
DEFAULT_OPTIMIZATION_RISK_WEIGHT = 0.40


@dataclass(frozen=True)
class OptimizationConfig:
    """
    Typed, immutable configuration for candidate route optimization.
    """
    distance_weight: float = DEFAULT_OPTIMIZATION_DISTANCE_WEIGHT
    risk_weight: float = DEFAULT_OPTIMIZATION_RISK_WEIGHT

    def __post_init__(self):
        if self.distance_weight < 0.0:
            raise ValueError(f"distance_weight must be >= 0, got {self.distance_weight}")
        if self.risk_weight < 0.0:
            raise ValueError(f"risk_weight must be >= 0, got {self.risk_weight}")
        total = self.distance_weight + self.risk_weight
        if total <= 0.0:
            raise ValueError(
                f"Sum of distance_weight ({self.distance_weight}) and "
                f"risk_weight ({self.risk_weight}) must be > 0"
            )

    @property
    def normalized_distance_weight(self) -> float:
        """
        Normalized distance weight in [0.0, 1.0].
        """
        return self.distance_weight / (self.distance_weight + self.risk_weight)

    @property
    def normalized_risk_weight(self) -> float:
        """
        Normalized risk weight in [0.0, 1.0].
        """
        return self.risk_weight / (self.distance_weight + self.risk_weight)


def get_optimization_config() -> OptimizationConfig:
    """
    Instantiate OptimizationConfig from Django settings, falling back to defaults.
    """
    distance_weight = float(
        getattr(settings, "OPTIMIZATION_DISTANCE_WEIGHT", DEFAULT_OPTIMIZATION_DISTANCE_WEIGHT)
    )
    risk_weight = float(
        getattr(settings, "OPTIMIZATION_RISK_WEIGHT", DEFAULT_OPTIMIZATION_RISK_WEIGHT)
    )
    return OptimizationConfig(
        distance_weight=distance_weight,
        risk_weight=risk_weight,
    )

