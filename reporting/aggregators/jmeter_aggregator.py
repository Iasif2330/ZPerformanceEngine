# reporting/aggregators/jmeter_aggregator.py
import json
from pathlib import Path
from typing import List, Tuple

from reporting.models.api_metrics import ApiMetrics
from reporting.models.run_metrics import RunMetrics


class JMeterAggregator:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.statistics_file = output_dir / "statistics.json"

    def aggregate(self) -> Tuple[List[ApiMetrics], RunMetrics]:
        if not self.statistics_file.exists():
            raise FileNotFoundError(
                f"statistics.json not found at {self.statistics_file}"
            )

        with open(self.statistics_file) as f:
            stats = json.load(f)

        api_metrics: List[ApiMetrics] = []

        for label, values in stats.items():
            if label == "Total":
                continue

            api_metrics.append(
                ApiMetrics(
                    api_name=label,
                    avg_ms=values["meanResTime"],
                    p95_ms=values["pct2ResTime"],
                    p99_ms=values["pct3ResTime"],
                    throughput_rps=values["throughput"],
                    error_rate_pct=values["errorPct"],
                    sample_count=values["sampleCount"],
                )
            )

        total = stats["Total"]

        run_metrics = RunMetrics(
            total_requests=total["sampleCount"],
            avg_ms=total["meanResTime"],
            p95_ms=total["pct2ResTime"],
            p99_ms=total["pct3ResTime"],
            throughput_rps=total["throughput"],
            error_rate_pct=total["errorPct"],
        )

        return api_metrics, run_metrics