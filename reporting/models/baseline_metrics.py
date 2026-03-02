# reporting/models/baseline_metrics.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class BaselineMetrics:
    overall_status: str        # IMPROVED / DEGRADED / STABLE
    latency_delta_pct: Optional[float]
    confidence: Optional[str]