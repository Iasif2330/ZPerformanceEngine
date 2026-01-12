# reasoning/correlators/correlator.py

from typing import Dict, List


class Correlator:
    """
    Correlates server-side telemetry with baselines
    and assigns severity using server rules.
    """

    def correlate(
        self,
        server_metrics: Dict,
        server_baseline: Dict | None,
        rules: Dict
    ) -> Dict:

        # If no server data at all
        if server_metrics is None or server_metrics.get("status") != "AVAILABLE":
            return {
                "status": "NOT_AVAILABLE",
                "signals": []
            }

        signals = []

        for sig in server_metrics.get("signals", []):
            metric = sig["metric"]
            current = sig["current"]

            baseline = None
            deviation_pct = None
            severity = None

            rule = rules["server_rules"].get(metric)
            if not rule:
                continue  # unknown / unsupported metric

            # Compute deviation if baseline exists
            if server_baseline and metric in server_baseline:
                baseline = server_baseline[metric]
                if baseline > 0:
                    deviation_pct = round(((current - baseline) / baseline) * 100, 2)

            # Assign severity
            severity = self._assign_severity(
                metric=metric,
                current=current,
                deviation_pct=deviation_pct,
                rule=rule
            )

            if severity:
                signals.append({
                    "metric": metric,
                    "current": current,
                    "baseline": baseline,
                    "deviation_pct": deviation_pct,
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
        metric: str,
        current: float,
        deviation_pct: float | None,
        rule: Dict
    ) -> str | None:
        """
        Apply server rules to determine severity.
        """

        # ✅ Absolute thresholds (preferred for servers)
        if "severe_abs" in rule:
            if current >= rule["severe_abs"]:
                return "SEVERE"
            if current >= rule["minor_abs"]:
                return "MINOR"
            return None

        # Percentage-based (only if baseline exists)
        if deviation_pct is not None:
            if deviation_pct >= rule.get("severe_pct", 9999):
                return "SEVERE"
            if deviation_pct >= rule.get("minor_pct", 9999):
                return "MINOR"

        return None