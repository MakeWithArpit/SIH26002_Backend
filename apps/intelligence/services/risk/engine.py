"""
Infrastructure Risk Engine.

Calculates explainable, rule-based disruption risk for road infrastructure segments
based on static landslide susceptibility, historical landslides, and dynamic
district-level weather snapshots.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.utils import timezone

from apps.intelligence.services.risk.config import RiskConfig, get_risk_config
from apps.intelligence.services.risk.factors import FactorAssessment, FactorEvaluator

logger = logging.getLogger(__name__)


@dataclass
class RiskAssessmentResult:
    """
    Structured, explainable risk assessment output.
    """
    score: float
    level: str
    factors: List[FactorAssessment]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level,
            "factors": [f.to_dict() for f in self.factors],
        }


class RiskEngine:
    """
    Central decision engine for assessing Infrastructure-level disruption risk.
    """

    @classmethod
    def classify_risk_level(cls, score: float, config: RiskConfig) -> str:
        """
        Classify a 0-100 risk score into low, medium, or high.
        - 0–39: LOW
        - 40–69: MEDIUM
        - 70–100: HIGH
        """
        if score <= config.threshold_low_max:
            return "low"
        elif score <= config.threshold_medium_max:
            return "medium"
        else:
            return "high"

    @classmethod
    def assess(
        cls,
        infrastructure: Any,
        config: Optional[RiskConfig] = None,
    ) -> RiskAssessmentResult:
        """
        Assess risk for a single Infrastructure segment without mutating or saving to DB.
        """
        active_config = config or get_risk_config()
        factors = FactorEvaluator.evaluate_all(infrastructure, active_config)

        raw_score = sum(f.contribution for f in factors)
        clamped_score = round(min(100.0, max(0.0, raw_score)), 1)
        level = cls.classify_risk_level(clamped_score, active_config)

        return RiskAssessmentResult(
            score=clamped_score,
            level=level,
            factors=factors,
        )

    @classmethod
    def assess_and_update(
        cls,
        infrastructure: Any,
        config: Optional[RiskConfig] = None,
    ) -> Any:
        """
        Assess risk and persist updated risk fields to the Infrastructure database record.
        Persisted fields:
        - risk_score
        - risk_level
        - risk_updated_at
        - top_factors
        """
        assessment = cls.assess(infrastructure, config=config)

        infrastructure.risk_score = assessment.score
        infrastructure.risk_level = assessment.level
        infrastructure.risk_updated_at = timezone.now()
        infrastructure.top_factors = [f.to_dict() for f in assessment.factors]

        update_fields = ["risk_score", "risk_level", "risk_updated_at", "top_factors"]
        if hasattr(infrastructure, "last_assessed_at"):
            infrastructure.last_assessed_at = timezone.now()
            update_fields.append("last_assessed_at")

        infrastructure.save(update_fields=update_fields)
        infrastructure.last_assessment = assessment

        logger.info(
            "Updated risk for Infrastructure #%s '%s': score=%.1f (%s)",
            getattr(infrastructure, "id", "N/A"),
            getattr(infrastructure, "name", "N/A"),
            assessment.score,
            assessment.level.upper(),
        )

        return infrastructure

    @classmethod
    def assess_and_update_batch(
        cls,
        infrastructures: Iterable[Any],
        config: Optional[RiskConfig] = None,
    ) -> Tuple[List[Any], List[Tuple[Any, Exception]]]:
        """
        Assess and persist a batch of Infrastructure segments with per-segment error isolation.
        Returns a tuple: (successful_records, list_of_errors)
        """
        successful = []
        errors = []
        active_config = config or get_risk_config()

        for infra in infrastructures:
            try:
                updated = cls.assess_and_update(infra, config=active_config)
                successful.append(updated)
            except Exception as e:
                logger.error(
                    "Error assessing risk for Infrastructure #%s: %s",
                    getattr(infra, "id", "unknown"),
                    e,
                    exc_info=True,
                )
                errors.append((infra, e))

        return successful, errors
