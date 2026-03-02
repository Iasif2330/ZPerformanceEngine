# reporting/models/api_metrics.py
from dataclasses import dataclass

@dataclass
class ApiMetrics:
    api_name: str
    avg_ms: float
    p95_ms: float
    p99_ms: float
    throughput_rps: float
    error_rate_pct: float
    sample_count: int