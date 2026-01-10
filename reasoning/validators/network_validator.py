# reasoning/validators/network_validator.py

from typing import Dict


class NetworkValidator:
    """
    Validates client → server network path health using
    independent network telemetry and environment-aware rules.
    """

    def __init__(self, rules: Dict, environment: str):
        self.rules = rules["network"]
        self.environment = environment

        # Environment-aware RTT thresholds (ms)
        self.rtt_thresholds = {
            "qa": {
                "avg_ms_max": 120,
                "p95_ms_max": 180,
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

    def validate(self, telemetry: Dict) -> Dict:
        issues = []

        # Select RTT thresholds for environment
        rtt_limits = self.rtt_thresholds.get(
            self.environment,
            self.rtt_thresholds["qa"],  # safe default
        )

        # ---- RTT checks ----
        rtt = telemetry.get("rtt", {})

        if rtt.get("avg_ms") is not None:
            if rtt["avg_ms"] >= rtt_limits["avg_ms_max"]:
                issues.append(
                    f"RTT avg {rtt['avg_ms']} ms exceeds "
                    f"{rtt_limits['avg_ms_max']} ms"
                )

        if rtt.get("p95_ms") is not None:
            if rtt["p95_ms"] >= rtt_limits["p95_ms_max"]:
                issues.append(
                    f"RTT p95 {rtt['p95_ms']} ms exceeds "
                    f"{rtt_limits['p95_ms_max']} ms"
                )

        # ---- Packet loss ----
        loss = telemetry.get("packet_loss", {})
        if loss.get("pct") is not None:
            if loss["pct"] >= self.rules["packet_loss"]["max_pct"]:
                issues.append(
                    f"Packet loss {loss['pct']}% exceeds "
                    f"{self.rules['packet_loss']['max_pct']}%"
                )

        # ---- Retransmissions ----
        retrans = telemetry.get("retransmissions", {})
        if retrans.get("pct") is not None:
            if retrans["pct"] >= self.rules["retransmissions"]["max_pct"]:
                issues.append(
                    f"TCP retransmissions {retrans['pct']}% exceeds "
                    f"{self.rules['retransmissions']['max_pct']}%"
                )

        # ---- Load balancer queue ----
        lb = telemetry.get("load_balancer", {})
        if lb.get("queue_time_p95_ms") is not None:
            if lb["queue_time_p95_ms"] >= self.rules["load_balancer"]["queue_time_p95_ms_max"]:
                issues.append(
                    f"LB queue time p95 {lb['queue_time_p95_ms']} ms exceeds "
                    f"{self.rules['load_balancer']['queue_time_p95_ms_max']} ms"
                )

        status = "NETWORK_OK" if not issues else "NETWORK_UNSTABLE"

        return {
            "status": status,
            "issues": issues,
            "environment": self.environment,
            "rtt_limits": rtt_limits,
        }