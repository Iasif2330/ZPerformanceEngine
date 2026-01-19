from typing import Dict, List


class Correlator:
    """
    Correlates server-side telemetry and derives server states
    + probabilistic attribution of likely causes.

    DESIGN PRINCIPLES:
    - Server correlation is NOT baseline-driven
    - Absolute thresholds only
    - State-based output (not metric-based)
    - Infra-only signals (NO APM)
    - No CI gating or auto-accept logic
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
          attribution: {
              distribution: {...},
              reason: str
          }
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
                "attribution": {},
            }

        ruleset = rules.get("server_rules", {})

        signals: List[Dict] = []

        # --------------------------------------------------
        # Initialize server states
        # --------------------------------------------------
        states = {
            "server_saturated": False,     # cpu_pct OR mem_pct
            "server_throttled": False,     # cpu_throttle_pct
            "server_mem_pressure": False,  # mem_pressure_pct
            "server_healthy": True,        # disproved later
        }

        # --------------------------------------------------
        # Evaluate each server signal
        # --------------------------------------------------
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

        # --------------------------------------------------
        # Final health resolution
        # --------------------------------------------------
        if (
            states["server_saturated"]
            or states["server_throttled"]
            or states["server_mem_pressure"]
        ):
            states["server_healthy"] = False

        status = "CONFIRMED" if signals else "NOT_CONFIRMED"

        # --------------------------------------------------
        # Attribution (probabilistic, explainable)
        # --------------------------------------------------
        attribution = self._derive_attribution(states)

        return {
            "status": status,
            "states": states,
            "signals": signals,
            "attribution": attribution,
        }

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
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

    def _derive_attribution(self, states: Dict) -> Dict:
        """
        Derive probabilistic attribution from server states.

        IMPORTANT:
        - This does NOT decide pass/fail
        - Percentages are relative likelihoods
        - Explanation is written for non-experts
        """

        # --------------------------------------------------
        # Base priors (roughly equal)
        # --------------------------------------------------
        attribution = {
            "capacity": 0.33,
            "execution": 0.33,
            "non_infra": 0.34,
        }

        # Track which signals influenced the outcome
        saw_throttling = False
        saw_saturation = False
        saw_mem_pressure = False
        saw_healthy = False

        # --------------------------------------------------
        # Evidence-based adjustments
        # --------------------------------------------------
        if states.get("server_saturated"):
            attribution["capacity"] += 0.30
            attribution["non_infra"] -= 0.15
            saw_saturation = True

        if states.get("server_throttled"):
            attribution["execution"] += 0.25
            attribution["capacity"] += 0.10
            saw_throttling = True

        if states.get("server_mem_pressure"):
            attribution["capacity"] += 0.25
            attribution["execution"] += 0.05
            saw_mem_pressure = True

        if states.get("server_healthy"):
            attribution["non_infra"] += 0.30
            attribution["capacity"] -= 0.15
            attribution["execution"] -= 0.15
            saw_healthy = True

        # --------------------------------------------------
        # Clamp (safety)
        # --------------------------------------------------
        for k in attribution:
            attribution[k] = max(attribution[k], 0.0)

        # --------------------------------------------------
        # Normalize to percentages
        # --------------------------------------------------
        total = sum(attribution.values())
        if total > 0:
            for k in attribution:
                attribution[k] = round(attribution[k] / total, 2)

        # --------------------------------------------------
        # Beginner-friendly rationale
        # --------------------------------------------------
        if saw_throttling:
            reason = (
                "CPU throttling was observed on the server, which usually indicates "
                "execution-related inefficiencies (such as thread contention or GC activity). "
                "This makes execution issues the most likely cause, with some contribution "
                "from capacity limits, while non-infrastructure causes are less likely."
            )
        elif saw_saturation:
            reason = (
                "Server resource usage reached saturation levels, which points strongly "
                "to capacity constraints as the primary cause of the observed behavior."
            )
        elif saw_mem_pressure:
            reason = (
                "Memory pressure was observed, suggesting possible memory contention or "
                "inefficient memory usage contributing to performance degradation."
            )
        elif saw_healthy:
            reason = (
                "Server infrastructure remained healthy during the test, which makes "
                "application-level or external (non-infrastructure) causes more likely."
            )
        else:
            reason = (
                "No strong server-side stress signals were detected, so no single cause "
                "dominates the attribution."
            )

        return {
            "distribution": attribution,
            "reason": reason
        }