# reporting/orchestrator.py
import os
from datetime import datetime
from pathlib import Path

from reporting.models.run_context import RunContext
from reporting.models.report_model import ReportModel

from reporting.aggregators.jmeter_aggregator import JMeterAggregator

from reporting.aggregators.baseline_aggregator import BaselineAggregator

from reporting.aggregators.infra_aggregator import InfraAggregator

from reporting.decisions.run_validity import RunValidity
from reporting.decisions.regression_status import RegressionStatus

from reporting.agents.llm_client import LLMClient
from reporting.agents.executive_agent import ExecutiveSummaryAgent

from reporting.agents.api_summary_agent import ApiSummaryAgent

from reporting.agents.infra_summary_agent import InfraSummaryAgent

from reporting.renderers.html_renderer import HtmlRenderer

from reporting.agents.local_llm_client import LocalLLMClient


class ReportOrchestrator:

    def __init__(self, workspace_path: str):
        self.workspace = Path(workspace_path)
        self.output_dir = self.workspace / "output"

        self.results_jtl = self.output_dir / "results.jtl"
        self.statistics_json = self.output_dir / "statistics.json"
        self.reasoning_report = self.output_dir / "reasoning" / "reasoning_report.json"
        self.executive_dir = self.output_dir / "executive"

    # ---------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------
    def validate_inputs(self):
        if not self.results_jtl.exists():
            raise FileNotFoundError(f"Missing results.jtl at {self.results_jtl}")

        if not self.statistics_json.exists():
            raise FileNotFoundError(f"Missing statistics.json at {self.statistics_json}")

        if not self.reasoning_report.exists():
            raise FileNotFoundError(
                f"Missing reasoning_report.json at {self.reasoning_report}"
            )

    # ---------------------------------------------------------
    # RUN CONTEXT
    # ---------------------------------------------------------
    def build_run_context(self) -> RunContext:
        start_ts = datetime.fromtimestamp(
            int((self.output_dir / "test_start_ts").read_text())
        )
        end_ts = datetime.fromtimestamp(
            int((self.output_dir / "test_end_ts").read_text())
        )

        return RunContext(
            environment=os.getenv("ENVIRONMENT", "unknown"),
            load_profile=os.getenv("LOAD_PROFILE", "unknown"),
            apis=["ALL"],  # resolved later via api-groups
            start_ts=start_ts,
            end_ts=end_ts
        )

    # ---------------------------------------------------------
    # MAIN ENTRY POINT
    # ---------------------------------------------------------
    def generate(self) -> ReportModel:
        self.validate_inputs()

        # 1️⃣ Context
        context = self.build_run_context()

        # 2️⃣ Client-side metrics (JMeter)
        jmeter_aggregator = JMeterAggregator(self.output_dir)
        api_metrics, run_metrics = jmeter_aggregator.aggregate()

        # 3️⃣ Baseline + infra summaries
        baseline_aggregator = BaselineAggregator(Path(self.reasoning_report))
        baseline_metrics = baseline_aggregator.aggregate()

        infra_aggregator = InfraAggregator(Path(self.reasoning_report))
        infra_metrics = infra_aggregator.aggregate()

        # 4️⃣ Base report (no decisions yet)
        base_report = ReportModel(
            context=context,
            run_metrics=run_metrics,
            api_metrics=api_metrics,
            infra_metrics=infra_metrics,
            baseline_metrics=baseline_metrics,
            is_valid=False,              # placeholder
            regression_label="UNKNOWN"   # placeholder
        )

        # 5️⃣ Report-level decisions
        is_valid = RunValidity.evaluate(base_report)
        regression_label = RegressionStatus.classify(base_report.baseline_metrics)

        # 6️⃣ Final report model
        report = ReportModel(
            context=context,
            run_metrics=run_metrics,
            api_metrics=api_metrics,
            infra_metrics=infra_metrics,
            baseline_metrics=baseline_metrics,
            is_valid=is_valid,
            regression_label=regression_label
        )

        llm = LocalLLMClient(model="mistral")
        executive_agent = ExecutiveSummaryAgent(llm)

        if report.is_valid:
            report.executive_summary = executive_agent.run(report)
        else:
            report.executive_summary = (
                "This performance run is invalid and should not be used for analysis."
            )

        # 8️⃣ Per-API AI summaries
        api_agent = ApiSummaryAgent(llm)
        report.api_summaries = {}

        if report.is_valid:
            for api in report.api_metrics:
                report.api_summaries[api.api_name] = api_agent.run(api, report)
        else:
            for api in report.api_metrics:
                report.api_summaries[api.api_name] = "Invalid run."

        
        # 9️⃣ Infra AI summary
        infra_agent = InfraSummaryAgent(llm)

        if report.is_valid:
            report.infra_summary = infra_agent.run(report)
        else:
            report.infra_summary = "Invalid run."

        # 🔟 Render HTML report
        try:
            renderer = HtmlRenderer()
            output_file = self.executive_dir / "index.html"
            renderer.render(report, output_file)
            print("✔ HTML report written to:", output_file)
        except Exception as e:
            print(f"⚠ HTML report rendering failed: {e}")

        # 🔍 Debug visibility
        print("\n✔ Workspace:", self.workspace)
        print("✔ APIs aggregated:", len(api_metrics))
        print("✔ Total requests:", run_metrics.total_requests)
        print("✔ Avg latency:", run_metrics.avg_ms)
        print("✔ Baseline metrics:", baseline_metrics)
        print("✔ Infra metrics:", infra_metrics)
        print("✔ Run valid:", is_valid)
        print("✔ Regression label:", regression_label)
        print("✔ Executive summary:", report.executive_summary)
        print("✔ API summaries:", report.api_summaries)
        print("✔ Infra summary:", report.infra_summary)

        return report