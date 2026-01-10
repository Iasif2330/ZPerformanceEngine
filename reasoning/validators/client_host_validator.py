# reasoning/validators/client_host_validator.py

from typing import Dict


class ClientHostValidator:
    """
    Validates load-generator host health using collected telemetry
    and predefined client host rules.
    """

    def __init__(self, rules: Dict):
        self.rules = rules["client_host"]

    def validate(self, telemetry: Dict) -> Dict:
        issues = []

        # ---- CPU checks ----
        cpu = telemetry["cpu"]
        if cpu["avg_pct"] >= self.rules["cpu"]["avg_pct_max"]:
            issues.append(
                f"CPU avg {cpu['avg_pct']}% exceeds "
                f"{self.rules['cpu']['avg_pct_max']}%"
            )

        if cpu["max_pct"] >= self.rules["cpu"]["max_pct_max"]:
            issues.append(
                f"CPU max {cpu['max_pct']}% exceeds "
                f"{self.rules['cpu']['max_pct_max']}%"
            )

        # ---- Memory checks ----
        mem = telemetry["memory"]
        if mem["avg_pct"] >= self.rules["memory"]["avg_pct_max"]:
            issues.append(
                f"Memory avg {mem['avg_pct']}% exceeds "
                f"{self.rules['memory']['avg_pct_max']}%"
            )

        if mem["max_pct"] >= self.rules["memory"]["max_pct_max"]:
            issues.append(
                f"Memory max {mem['max_pct']}% exceeds "
                f"{self.rules['memory']['max_pct_max']}%"
            )

        # ---- Load average checks ----
        os_stats = telemetry["os"]
        cores = cpu["cores"]
        load_per_core = os_stats["load_avg_1m"] / cores

        if load_per_core >= self.rules["os"]["load_avg_per_core_max"]:
            issues.append(
                f"Load avg per core {round(load_per_core, 2)} exceeds "
                f"{self.rules['os']['load_avg_per_core_max']}"
            )

        status = "CLIENT_HOST_OK" if not issues else "CLIENT_HOST_UNSTABLE"

        return {
            "status": status,
            "issues": issues
        }