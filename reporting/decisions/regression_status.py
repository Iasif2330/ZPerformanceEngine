# reporting/decisions/regression_status.py
from typing import Optional
from reporting.models.baseline_metrics import BaselineMetrics


class RegressionStatus:
    @staticmethod
    def classify(baseline: Optional[BaselineMetrics]) -> str:
        if baseline is None:
            return "UNKNOWN"

        if baseline.overall_status == "IMPROVED":
            return "GREEN"

        if baseline.overall_status == "STABLE":
            return "GREEN"

        if baseline.overall_status == "DEGRADED":
            if baseline.confidence == "HIGH":
                return "RED"
            return "AMBER"

        return "UNKNOWN"