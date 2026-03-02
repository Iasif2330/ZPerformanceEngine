import json
from reporting.models.infra_metrics import InfraMetrics


class InfraAggregator:
    def __init__(self, reasoning_report_path: str):
        self.reasoning_report_path = reasoning_report_path

    def aggregate(self):
        with open(self.reasoning_report_path) as f:
            data = json.load(f)

        server_corr = data.get("server_correlation")
        if not server_corr:
            return None

        states = server_corr.get("states", {})
        attribution = server_corr.get("attribution", {})

        return InfraMetrics(
            status=server_corr.get("status"),
            server_throttled=states.get("server_throttled", False),
            server_saturated=states.get("server_saturated", False),
            server_mem_pressure=states.get("server_mem_pressure", False),
            attribution_distribution=attribution.get("distribution", {}),
            attribution_reason=attribution.get("reason", ""),
        )