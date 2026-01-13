from typing import Dict, List


class Correlator:
    """
    Correlates server-side telemetry and derives server states.

    DESIGN PRINCIPLES:
    - Server correlation is NOT baseline-driven
    - Absolute thresholds only (capacity & health signals)
    - All server metrics are evaluated every time
    - Client metrics are NOT used here
    - Output is state-based, not metric-based
    """

    def correlate(
        self,
        server_metrics: Dict,
        server_baseline: Dict | None,  # kept for backward compatibility
        rules: Dict
    ) -> Dict:
        """
        Correlate server metrics and derive server states.

        Returns:
            {
              status: CONFIRMED | NOT_CONFIRMED | NOT_AVAILABLE
              states: {...}
              signals: [...]
            }
        """

        # --------------------------------------------------
        # No server data
        # --------------------------------------------------
        if server_metrics is None or server_metrics.get("status") != "AVAILABLE":
            return {
                "status": "NOT_AVAILABLE",
                "states": {},
                "signals": [],
            }

        ruleset = rules.get("server_rules", {})

        signals: List[Dict] = []

        # --------------------------------------------------
        # Server state flags (derived, not guessed)
        # --------------------------------------------------
        states = {
            "server_saturated": False,
            "server_slow": False,
            "server_erroring": False,
            "server_healthy": True,  # assume healthy, disprove later
        }

        # --------------------------------------------------
        # Evaluate all server metrics
        # --------------------------------------------------
        for sig in server_metrics.get("signals", []):
            metric = sig.get("metric")
            current = sig.get("current")

            rule = ruleset.get(metric)
            if not rule or current is None:
                continue  # unsupported or missing metric

            severity = self._assign_severity(
                current=current,
                rule=rule
            )

            # Record signal if threshold crossed
            if severity:
                signals.append({
                    "metric": metric,
                    "current": current,
                    "severity": severity,
                })

                # ------------------------------------------
                # Derive server states (objective rules)
                # ------------------------------------------
                if metric in ("cpu_pct", "memory_pct", "jvm_threads"):
                    states["server_saturated"] = True

                if metric == "server_latency_p95_ms":
                    states["server_slow"] = True

                if metric == "http5xx_rate":
                    states["server_erroring"] = True

        # --------------------------------------------------
        # Final state resolution
        # --------------------------------------------------
        if states["server_saturated"] or states["server_slow"] or states["server_erroring"]:
            states["server_healthy"] = False

        status = "CONFIRMED" if signals else "NOT_CONFIRMED"

        return {
            "status": status,
            "states": states,
            "signals": signals,
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
        {
          minor_abs: <number>,
          severe_abs: <number>
        }
        """

        severe = rule.get("severe_abs")
        minor = rule.get("minor_abs")

        if severe is not None and current >= severe:
            return "SEVERE"

        if minor is not None and current >= minor:
            return "MINOR"

        return None