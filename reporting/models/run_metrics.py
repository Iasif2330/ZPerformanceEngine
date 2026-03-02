# reporting/models/run_metrics.py
from dataclasses import dataclass

@dataclass
class RunMetrics:
    total_requests: int
    avg_ms: float
    p95_ms: float
    p99_ms: float
    throughput_rps: float
    error_rate_pct: float