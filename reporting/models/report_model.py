# reporting/models/report_model.py
from dataclasses import dataclass
from typing import List, Optional

from .run_context import RunContext
from .run_metrics import RunMetrics
from .api_metrics import ApiMetrics
from .infra_metrics import InfraMetrics
from .baseline_metrics import BaselineMetrics


@dataclass
class ReportModel:
    context: RunContext
    run_metrics: RunMetrics
    api_metrics: List[ApiMetrics]
    infra_metrics: Optional[InfraMetrics]
    baseline_metrics: Optional[BaselineMetrics]

    # 🧠 Report-level decisions
    is_valid: bool
    regression_label: str

    # 🤖 AI-generated content (optional)
    executive_summary: Optional[str] = None
    api_summaries: Optional[dict] = None
    infra_summary: Optional[str] = None