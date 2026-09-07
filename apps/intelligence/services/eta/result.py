"""
Result Dataclasses for ETA Estimation Engine.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ETAFactorAdjustment:
    """
    Detailed breakdown of a single condition adjustment factor.
    """
    category: str
    name: str
    delay_minutes: float
    multiplier: float = 1.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "delay_minutes": round(self.delay_minutes, 1),
            "multiplier": round(self.multiplier, 2),
            "description": self.description,
        }


@dataclass
class ETAResult:
    """
    Comprehensive, explainable ETA and delay calculation result.
    """
    route_id: str
    distance_km: float
    base_eta_minutes: float
    adjusted_eta_minutes: float
    expected_delay_minutes: float
    delay_severity: str
    start_time: Optional[datetime] = None
    estimated_arrival_time: Optional[datetime] = None
    adjustments: List[ETAFactorAdjustment] = field(default_factory=list)
    top_factors: List[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize ETA result with standard rounding and ISO 8601 datetimes.
        """
        return {
            "route_id": self.route_id,
            "distance_km": round(self.distance_km, 2),
            "base_eta_minutes": round(self.base_eta_minutes, 1),
            "adjusted_eta_minutes": round(self.adjusted_eta_minutes, 1),
            "expected_delay_minutes": round(self.expected_delay_minutes, 1),
            "delay_severity": self.delay_severity,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "estimated_arrival_time": (
                self.estimated_arrival_time.isoformat() if self.estimated_arrival_time else None
            ),
            "adjustments": [adj.to_dict() for adj in self.adjustments],
            "top_factors": self.top_factors,
            "explanation": self.explanation,
        }

