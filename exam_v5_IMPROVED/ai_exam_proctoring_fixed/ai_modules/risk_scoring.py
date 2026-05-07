# ai_modules/risk_scoring.py - ML-based cheating risk scorer

from config import RISK_WEIGHTS, RISK_THRESHOLDS


class RiskScorer:
    """
    Calculates a cheating probability score (0-100) from violation counts.
    Uses weighted feature aggregation.
    Outputs: Low Risk / Medium Risk / High Risk
    """

    def calculate(self, violation_counts: dict) -> tuple:
        """
        Args:
            violation_counts: dict mapping violation_type -> count
                e.g. {"phone_detected": 2, "no_face": 5, ...}
        Returns:
            (risk_score: float 0-100, risk_level: str)
        """
        # Build raw weighted score
        raw = sum(
            RISK_WEIGHTS.get(vtype, 5) * count
            for vtype, count in violation_counts.items()
        )
        # Clamp to 0-100
        score = min(100.0, max(0.0, float(raw)))

        if score <= RISK_THRESHOLDS["low"]:
            level = "Low Risk"
        elif score <= RISK_THRESHOLDS["medium"]:
            level = "Medium Risk"
        else:
            level = "High Risk"

        return round(score, 1), level

    def feature_vector(self, violation_counts: dict) -> dict:
        """Return per-feature contributions for dashboard breakdown."""
        return {
            vtype: RISK_WEIGHTS.get(vtype, 5) * violation_counts.get(vtype, 0)
            for vtype in RISK_WEIGHTS
        }
