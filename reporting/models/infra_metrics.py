class InfraMetrics:
    def __init__(
        self,
        status: str,
        server_throttled: bool,
        server_saturated: bool,
        server_mem_pressure: bool,
        attribution_distribution: dict,
        attribution_reason: str,
    ):
        self.status = status
        self.server_throttled = server_throttled
        self.server_saturated = server_saturated
        self.server_mem_pressure = server_mem_pressure
        self.attribution_distribution = attribution_distribution
        self.attribution_reason = attribution_reason