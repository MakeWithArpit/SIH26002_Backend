"""
Result dataclasses for Route Risk Engine.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class RouteSegmentRisk:
    """
    Risk profile of an individual directed road segment within a route.
    """
    infrastructure_id: int
    name: str
    edge_identity: Optional[Tuple[Any, Any, Any]] = None  # (u, v, key)
    length_km: float = 0.0
    risk_score: float = 0.0
    risk_level: str = "low"
    top_factors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "infrastructure_id": self.infrastructure_id,
            "name": self.name,
            "edge_identity": list(self.edge_identity) if self.edge_identity is not None else None,
            "length_km": round(self.length_km, 3),
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level,
            "top_factors": self.top_factors,
        }


@dataclass
class FactorContributionSummary:
    """
    Aggregated factor contribution across all segments of a route.
    """
    factor_name: str
    total_contribution: float
    affected_segments_count: int
    max_single_contribution: float
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factor_name": self.factor_name,
            "total_contribution": round(self.total_contribution, 2),
            "affected_segments_count": self.affected_segments_count,
            "max_single_contribution": round(self.max_single_contribution, 2),
            "description": self.description,
        }


@dataclass
class RouteRiskResult:
    """
    Comprehensive, explainable route-level risk assessment result.
    """
    route_score: float
    route_level: str
    max_segment_score: float
    highest_risk_segments: List[RouteSegmentRisk]
    segment_count: int
    high_risk_segment_count: int
    medium_risk_segment_count: int
    low_risk_segment_count: int
    total_length_km: float
    segments: List[RouteSegmentRisk]
    factor_summary: List[FactorContributionSummary]
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_score": round(self.route_score, 1),
            "route_level": self.route_level,
            "max_segment_score": round(self.max_segment_score, 1),
            "highest_risk_segments": [s.to_dict() for s in self.highest_risk_segments],
            "segment_count": self.segment_count,
            "high_risk_segment_count": self.high_risk_segment_count,
            "medium_risk_segment_count": self.medium_risk_segment_count,
            "low_risk_segment_count": self.low_risk_segment_count,
            "total_length_km": round(self.total_length_km, 2),
            "segments": [s.to_dict() for s in self.segments],
            "factor_summary": [f.to_dict() for f in self.factor_summary],
            "explanation": self.explanation,
        }
