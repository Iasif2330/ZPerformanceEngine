# reporting/models/infra_metrics.py
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class InfraMetrics:
    status: str
    server_throttled: bool
    server_saturated: bool
    server_mem_pressure: bool
    attribution_distribution: Dict[str, float]
    attribution_reason: str