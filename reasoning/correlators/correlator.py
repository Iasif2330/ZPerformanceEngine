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
          attribution: {...}
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
        # Bayesian-style attribution (SAFE, INLINE)
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
        This does NOT decide pass/fail — only likelihoods.
        """

        attribution = {
            "capacity": 0.33,
            "execution": 0.33,
            "non_infra": 0.34,
        }

        reasons = []

        if states.get("server_saturated"):
            attribution["capacity"] += 0.30
            attribution["non_infra"] -= 0.15
            reasons.append("server saturation increased capacity likelihood")

        if states.get("server_throttled"):
            attribution["execution"] += 0.25
            attribution["capacity"] += 0.10
            reasons.append("CPU throttling increased execution and capacity likelihood")

        if states.get("server_mem_pressure"):
            attribution["capacity"] += 0.25
            attribution["execution"] += 0.05
            reasons.append("memory pressure increased capacity likelihood")

        if states.get("server_healthy"):
            attribution["non_infra"] += 0.30
            attribution["capacity"] -= 0.15
            attribution["execution"] -= 0.15
            reasons.append("healthy infrastructure increased non-infra likelihood")

        # Clamp
        for k in attribution:
            attribution[k] = max(attribution[k], 0.0)

        total = sum(attribution.values())
        if total > 0:
            for k in attribution:
                attribution[k] = round(attribution[k] / total, 2)

        return {
            "distribution": attribution,
            "reason": "; ".join(reasons) if reasons else "no significant server signals"
        }