# reasoning/correlators/correlator.py

from typing import Dict, List


class Correlator:
    """
    Correlates server-side telemetry using absolute server rules.

    IMPORTANT DESIGN NOTE:
    - Server correlation is NOT baseline-driven.
    - Baseline & deviation fields are intentionally NOT included
      to avoid misleading outputs.
    """

    def correlate(
        self,
        server_metrics: Dict,
        server_baseline: Dict | None,  # kept for backward compatibility
        rules: Dict
    ) -> Dict:

        # If no server data at all
        if server_metrics is None or server_metrics.get("status") != "AVAILABLE":
            return {
                "status": "NOT_AVAILABLE",
                "signals": []
            }

        signals: List[Dict] = []

        for sig in server_metrics.get("signals", []):
            metric = sig["metric"]
            current = sig["current"]

            rule = rules.get("server_rules", {}).get(metric)
            if not rule:
                continue  # unsupported / unknown metric

            severity = self._assign_severity(
                current=current,
                rule=rule
            )

            if severity:
                signals.append({
                    "metric": metric,
                    "current": current,
                    "severity": severity
                })

        status = "CONFIRMED" if signals else "NOT_CONFIRMED"

        return {
            "status": status,
            "signals": signals
        }

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _assign_severity(
        self,
        current: float,
        rule: Dict
    ) -> str | None:
        """
        Apply absolute server thresholds.

        Expected rule format:
        - minor_abs
        - severe_abs
        """

        severe = rule.get("severe_abs")
        minor = rule.get("minor_abs")

        if severe is not None and current >= severe:
            return "SEVERE"

        if minor is not None and current >= minor:
            return "MINOR"

        return None