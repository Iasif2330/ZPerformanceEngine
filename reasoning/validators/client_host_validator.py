# reasoning/validators/client_host_validator.py

from typing import Dict, List


class ClientHostValidator:
    """
    Validates load-generator host health using collected telemetry
    and predefined client host rules.

    This validator:
    - Applies hard fail-fast invariants
    - Produces violations, not decisions
    - Does NOT interpret performance impact
    """

    def __init__(self, rules: Dict):
        self.rules = rules["client_host"]
        self.fail_fast = rules.get("behavior", {}).get("fail_fast", False)

    def validate(self, telemetry: Dict) -> Dict:
        violations: List[Dict] = []

        # ---- CPU checks ----
        cpu = telemetry["cpu"]
        self._check_max(
            violations, "cpu.avg_pct", cpu["avg_pct"],
            self.rules["cpu"]["avg_pct_max"]
        )
        self._check_max(
            violations, "cpu.max_pct", cpu["max_pct"],
            self.rules["cpu"]["max_pct_max"]
        )

        # ---- Memory checks ----
        mem = telemetry["memory"]
        self._check_max(
            violations, "memory.avg_pct", mem["avg_pct"],
            self.rules["memory"]["avg_pct_max"]
        )
        self._check_max(
            violations, "memory.max_pct", mem["max_pct"],
            self.rules["memory"]["max_pct_max"]
        )

        # Swap is binary
        if "swap_used_pct_max" in self.rules["memory"]:
            self._check_max(
                violations, "memory.swap_used_pct", mem["swap_used_pct"],
                self.rules["memory"]["swap_used_pct_max"]
            )

        # ---- Disk IO checks ----
        disk = telemetry.get("disk", {})
        if disk:
            self._check_max(
                violations, "disk.iowait_avg_pct",
                disk["iowait_avg_pct"],
                self.rules["disk"]["iowait_avg_pct_max"]
            )
            self._check_max(
                violations, "disk.iowait_max_pct",
                disk["iowait_max_pct"],
                self.rules["disk"]["iowait_max_pct_max"]
            )

        # ---- Network checks ----
        network = telemetry.get("network", {})
        if network:
            min_tx = self.rules["network"]["tx_bytes_per_sec_min"]
            if network["tx_bytes_per_sec"] < min_tx:
                violations.append({
                    "metric": "network.tx_bytes_per_sec",
                    "observed": network["tx_bytes_per_sec"],
                    "threshold": f">= {min_tx}",
                    "rule": "tx_bytes_per_sec_min"
                })

        # ---- Load average checks ----
        os_stats = telemetry["os"]
        cores = cpu["cores"]
        load_per_core = os_stats["load_avg_1m"] / cores

        self._check_max(
            violations, "os.load_avg_per_core",
            round(load_per_core, 2),
            self.rules["os"]["load_avg_per_core_max"]
        )

        return {
            "component": "client_host",
            "violations": violations,
            "healthy": len(violations) == 0,
            "fail_fast": self.fail_fast and len(violations) > 0
        }

    @staticmethod
    def _check_max(violations, metric, observed, max_allowed):
        if observed >= max_allowed:
            violations.append({
                "metric": metric,
                "observed": observed,
                "threshold": f"< {max_allowed}",
                "rule": "max"
            })