from typing import Dict, List


class DecisionEngine:
    """
    Final CI gating decision engine.

    Decisions are based on:
    - Client-side anomaly detection
    - Server-side state correlation (NOT raw metrics)
    - Explicit auto-accept rules

    This engine does NOT:
    - Guess root cause
    - Perform metric-to-metric mapping
    """

    def __init__(self, rules: Dict):
        self.rules = rules["auto_accept"]
        self.confidence_rules = rules.get("confidence", {})

    def decide(
        self,
        client_anomaly: Dict,
        server_correlation: Dict | None
    ) -> Dict:

        reasons: List[str] = []

        status = client_anomaly.get("status")
        anomalies = client_anomaly.get("anomalies", {})
        baseline_meta = client_anomaly.get("baseline_meta")

        # --------------------------------------------------
        # 1. No baseline / learning phase
        # --------------------------------------------------
        if status == "NO_BASELINE":
            if not self.rules.get("allow_no_baseline", False):
                return self._review(
                    "No baseline available for client metrics",
                    confidence="LOW"
                )

            return self._accept(
                "Baseline learning phase (no anomalies enforced)",
                confidence="LOW"
            )

        if status == "WEAK_BASELINE":
            reasons.append(
                f"Weak baseline (samples={baseline_meta.get('sample_count')})"
            )

        # --------------------------------------------------
        # 2. No client anomaly → auto accept
        # --------------------------------------------------
        if status == "OK":
            return self._accept(
                "No client-side anomalies detected",
                confidence="HIGH"
            )

        # --------------------------------------------------
        # 3. Too many client anomalies
        # --------------------------------------------------
        if len(anomalies) > self.rules.get("max_client_anomalies", 1):
            return self._review(
                "Multiple client-side anomalies detected",
                confidence="MEDIUM"
            )

        # --------------------------------------------------
        # 4. Server correlation required?
        # --------------------------------------------------
        if self.rules.get("require_server_confirmation", True):

            if server_correlation is None:
                return self._review(
                    "Server correlation missing",
                    confidence="LOW"
                )

            if server_correlation.get("status") != "CONFIRMED":
                return self._review(
                    "Server metrics did not corroborate client anomaly",
                    confidence="MEDIUM"
                )

        # --------------------------------------------------
        # 5. Interpret anomalies using SERVER STATES
        # --------------------------------------------------
        states = server_correlation.get("states", {}) if server_correlation else {}

        server_healthy = states.get("server_healthy", False)
        server_saturated = states.get("server_saturated", False)
        server_slow = states.get("server_slow", False)
        server_erroring = states.get("server_erroring", False)

        # ---- Error-rate anomaly handling ----
        if "error_rate" in anomalies:

            if server_healthy:
                return self._review(
                    "High client error rate observed while server capacity and latency are healthy",
                    confidence="HIGH"
                )

            if server_erroring:
                return self._review(
                    "Client errors corroborated by server-side errors",
                    confidence="HIGH"
                )

        # ---- Latency anomaly handling ----
        latency_anomalies = [
            k for k in anomalies.keys()
            if k.startswith("p95_latency") or k.startswith("p99_latency")
        ]

        if latency_anomalies:

            if server_saturated:
                return self._review(
                    "Client latency regression correlated with server saturation",
                    confidence="HIGH"
                )

            if server_slow:
                return self._review(
                    "Client latency regression correlated with server-side latency",
                    confidence="HIGH"
                )

            if server_healthy:
                return self._review(
                    "Client latency regression observed while server metrics remain healthy",
                    confidence="MEDIUM"
                )

        # ---- Throughput anomaly handling ----
        if "throughput" in anomalies:

            if server_saturated:
                return self._review(
                    "Throughput drop correlated with server resource saturation",
                    confidence="HIGH"
                )

            if server_healthy:
                return self._review(
                    "Throughput drop observed while server capacity is healthy",
                    confidence="MEDIUM"
                )

        # --------------------------------------------------
        # 6. Default conservative decision
        # --------------------------------------------------
        return self._review(
            "Client anomaly detected with inconclusive server correlation",
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