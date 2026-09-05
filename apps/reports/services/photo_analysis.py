"""
Photo Analysis CV Service — replaceable stub.

Phase 1: Returns a deterministic mock result echoing the officer's
reported incident_type and severity with high confidence.

Phase 5: Replace the body of `analyse()` with the real CV model call
(Om Ji's AI component). The return contract stays identical.
"""
import logging

from apps.reports.models import IncidentReport, AnalysisStatus

logger = logging.getLogger(__name__)


def analyse(report: IncidentReport) -> dict:
    """
    Run photo analysis on an IncidentReport and return a structured result.

    Returns:
        dict with keys: issue_type, severity, confidence

    Contract (matches AI/ML team spec):
        {
            "issue_type": "flood",
            "severity": "high",
            "confidence": 0.91
        }
    """
    try:
        # ── Stub: echo the officer's assessment with fixed confidence ──
        # Replace this block with real CV inference in Phase 5.
        result = {
            'issue_type': report.incident_type,
            'severity': report.severity,
            'confidence': 0.91,
        }

        # Persist AI fields on the report
        report.ai_issue_type = result['issue_type']
        report.ai_severity = result['severity']
        report.ai_confidence = result['confidence']
        report.analysis_status = AnalysisStatus.COMPLETED
        report.save(update_fields=[
            'ai_issue_type', 'ai_severity', 'ai_confidence', 'analysis_status',
        ])

        logger.info(
            'Photo analysis completed for report %s: %s',
            report.pk, result,
        )
        return result

    except Exception:
        logger.exception('Photo analysis failed for report %s', report.pk)
        report.analysis_status = AnalysisStatus.FAILED
        report.save(update_fields=['analysis_status'])
        return {}
