from typing import Dict, List


class Correlator:
    """
    Correlates server-side telemetry and derives server states.

    DESIGN PRINCIPLES:
    - Server correlation is NOT baseline-driven
    - Absolute thresholds only
    - State-based output (not metric-based)
    - Uses ONLY infra-level signals (no APM)
    """

    def correlate(
        self,
        server_metrics: Dict,
        server_baseline: Dict | None,  # backward compatibility
        rules: Dict
    ) -> Dict:
        """
        Returns:
        {
          status: CONFIRMED | NOT_CONFIRMED | NOT_AVAILABLE
          states: {...}
          signals: [...]
        }
        """

        # -------------------------------
        # No server data
        # -------------------------------
        if server_metrics is None or server_metrics.get("status") != "AVAILABLE":
            return {
                "status": "NOT_AVAILABLE",
                "states": {},
                "signals": [],
            }

        ruleset = rules.get("server_rules", {})

        signals: List[Dict] = []

        # -------------------------------
        # Initialize server states
        # -------------------------------
        states = {
            "server_saturated": False,     # cpu_pct OR mem_pct
            "server_throttled": False,     # cpu_throttle_pct
            "server_mem_pressure": False,  # mem_pressure_pct
            "server_healthy": True,        # disproved later
        }

        # -------------------------------
        # Evaluate each server signal
        # -------------------------------
        for sig in server_metrics.get("signals", []):
            metric = sig.get("metric")
            current = sig.get("current")

            rule = ruleset.get(metric)
            if rule is None or current is None:
                continue

            severity = self._assign_severity(current, rule)

            if severity:
                signals.append({
                    "metric": metric,
                    "current": current,
                    "severity": severity,
                })

                # ---------------------------
                # Derive states (OBJECTIVE)
                # ---------------------------
                if metric in ("cpu_pct", "mem_pct"):
                    states["server_saturated"] = True

                if metric == "cpu_throttle_pct":
                    states["server_throttled"] = True

                if metric == "mem_pressure_pct":
                    states["server_mem_pressure"] = True

        # -------------------------------
        # Final health resolution
        # -------------------------------
        if (
            states["server_saturated"]
            or states["server_throttled"]
            or states["server_mem_pressure"]
        ):
            states["server_healthy"] = False

        status = "CONFIRMED" if signals else "NOT_CONFIRMED"

        return {
            "status": status,
            "states": states,
            "signals": signals,
        }

    # -------------------------------
    # Helpers
    # -------------------------------
    def _assign_severity(self, current: float, rule: Dict) -> str | None:
        """
        rule format:
        {
          minor_abs: number,
          severe_abs: number
        }
        """

        severe = rule.get("severe_abs")
        minor = rule.get("minor_abs")

        if severe is not None and current >= severe:
            return "SEVERE"

        if minor is not None and current >= minor:
            return "MINOR"

        return None