# reasoning/validators/network_validator.py

from typing import Dict, List


class NetworkValidator:
    """
    Validates client → server network path health.

    Responsibilities:
    - Apply environment-aware, deterministic invariants
    - Emit structured violations
    - Signal fail-fast
    - NOT interpret performance impact
    """

    def __init__(self, rules: Dict, environment: str):
        self.rules = rules["network"]
        self.environment = environment

        # Environment-aware RTT thresholds (ms)
        self.rtt_thresholds = {
            "qa": {
                "avg_ms_max": 240,
                "p95_ms_max": 360,
            },
            "staging": {
                "avg_ms_max": 80,
                "p95_ms_max": 120,
            },
            "prod": {
                "avg_ms_max": self.rules["rtt"]["avg_ms_max"],
                "p95_ms_max": self.rules["rtt"]["p95_ms_max"],
            },
        }

        self.fail_fast = rules.get("behavior", {}).get("fail_fast", False)

    def validate(self, telemetry: Dict) -> Dict:
        violations: List[Dict] = []

        # Select RTT thresholds for environment
        rtt_limits = self.rtt_thresholds.get(
            self.environment,
            self.rtt_thresholds["qa"],  # safe default
        )

        # -------------------------------------------------
        # RTT checks (TCP connect latency)
        # -------------------------------------------------
        rtt = telemetry.get("rtt", {})

        if rtt.get("avg_ms") is not None:
            self._check_max(
                violations,
                "network.rtt.avg_ms",
                rtt["avg_ms"],
                rtt_limits["avg_ms_max"]
            )

        if rtt.get("p95_ms") is not None:
            self._check_max(
                violations,
                "network.rtt.p95_ms",
                rtt["p95_ms"],
                rtt_limits["p95_ms_max"]
            )

        # -------------------------------------------------
        # Packet loss (TCP connect failures)
        # -------------------------------------------------
        loss = telemetry.get("packet_loss", {})
        if loss.get("pct") is not None:
            self._check_max(
                violations,
                "network.packet_loss.pct",
                loss["pct"],
                self.rules["packet_loss"]["pct_max"]
            )

        return {
            "component": "network",
            "environment": self.environment,
            "rtt_limits": rtt_limits,
            "violations": violations,
            "healthy": len(violations) == 0,
            "fail_fast": self.fail_fast and len(violations) > 0
        }

    @staticmethod
    def _check_max(
        violations: List[Dict],
        metric: str,
        observed: float,
        max_allowed: float
    ):
        if observed >= max_allowed:
            violations.append({
                "metric": metric,
                "observed": observed,
                "threshold": f"< {max_allowed}",
                "rule": "max"
            })