# reasoning/decisions/decision_engine.py

from typing import Dict, List


class DecisionEngine:
    """
    Final CI gating decision engine.
    Uses client anomaly + server correlation + auto-accept rules.
    """

    def __init__(self, rules: Dict):
        self.rules = rules["auto_accept"]
        self.confidence_rules = rules["confidence"]

    def decide(
        self,
        client_anomaly: Dict,
        server_correlation: Dict | None
    ) -> Dict:

        reasons: List[str] = []

        status = client_anomaly.get("status")
        anomalies = client_anomaly.get("anomalies", {})

        # --------------------------------------------------
        # 1. No baseline handling
        # --------------------------------------------------
        if status == "NO_BASELINE":
            if not self.rules["allow_no_baseline"]:
                return self._review(
                    "No baseline available",
                    confidence="LOW"
                )

        # --------------------------------------------------
        # 2. No anomaly → auto accept
        # --------------------------------------------------
        if status == "OK":
            return self._accept(
                "No client-side anomalies detected",
                confidence="HIGH"
            )

        # --------------------------------------------------
        # 3. Client anomaly count check
        # --------------------------------------------------
        if len(anomalies) > self.rules["max_client_anomalies"]:
            return self._review(
                "Multiple client-side anomalies detected",
                confidence="MEDIUM"
            )

        # --------------------------------------------------
        # 4. Server correlation required?
        # --------------------------------------------------
        if self.rules["require_server_confirmation"]:

            if server_correlation is None:
                return self._review(
                    "Server correlation missing",
                    confidence="LOW"
                )

            if server_correlation["status"] != "CONFIRMED":
                return self._review(
                    "Server metrics did not corroborate client anomaly",
                    confidence="MEDIUM"
                )

        # --------------------------------------------------
        # 5. Server signal count
        # --------------------------------------------------
        server_signals = server_correlation.get("signals", [])

        if len(server_signals) > self.rules["max_server_signals"]:
            return self._review(
                "Multiple server-side signals detected",
                confidence="HIGH"
            )

        # --------------------------------------------------
        # 6. Severity check
        # --------------------------------------------------
        severe_limit = self.rules["severe_multiplier"]

        for sig in server_signals:
            if sig["severity"] == "SEVERE":
                return self._review(
                    f"Severe server deviation detected: {sig['metric']}",
                    confidence="HIGH"
                )

        # --------------------------------------------------
        # 7. Auto-accept
        # --------------------------------------------------
        return self._accept(
            "Single client anomaly corroborated by single server signal",
            confidence="MEDIUM"
        )

    # -------------------------
    # Helpers
    # -------------------------

    def _accept(self, reason: str, confidence: str) -> Dict:
        return {
            "decision": "AUTO_ACCEPT",
            "confidence": confidence,
            "reasons": [reason]
        }

    def _review(self, reason: str, confidence: str) -> Dict:
        return {
            "decision": "REVIEW_REQUIRED",
            "confidence": confidence,
            "reasons": [reason]
        }