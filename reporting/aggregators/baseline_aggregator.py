# reporting/aggregators/baseline_aggregator.py
import json
from pathlib import Path
from typing import Optional

from reporting.models.baseline_metrics import BaselineMetrics


class BaselineAggregator:
    def __init__(self, reasoning_report_path: Path):
        self.reasoning_report_path = reasoning_report_path

    def aggregate(self) -> Optional[BaselineMetrics]:
        if not self.reasoning_report_path.exists():
            return None

        with open(self.reasoning_report_path) as f:
            data = json.load(f)

        comparison = data.get("baseline_comparison")
        if not comparison:
            return None

        overall_status = comparison.get("overall_status", "UNKNOWN")

        latency_info = comparison.get("latency", {})
        latency_delta = latency_info.get("delta_pct")
        confidence = latency_info.get("confidence")

        return BaselineMetrics(
            overall_status=overall_status,
            latency_delta_pct=latency_delta,
            confidence=confidence
        )