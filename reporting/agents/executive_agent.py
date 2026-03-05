from reporting.models.report_model import ReportModel
from reporting.agents.local_llm_client import LocalLLMClient


class ExecutiveSummaryAgent:
    """
    Generates an executive-level summary of the performance run.
    Explanation only. No decisions.
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def run(self, report: ReportModel) -> str:
        # Hard gate: never explain invalid runs
        if not report.is_valid:
            return (
                "The performance run was marked as invalid and should not be "
                "used for performance analysis."
            )

        # ---------------------------
        # System prompt (ROLE + RULES)
        # ---------------------------
        system_prompt = (
            "You are a senior performance engineer writing for technical leadership.\n"
            "Rules:\n"
            "- Write short, clear sentences.\n"
            "- One idea per sentence in bullet points. New line for every point.\n"
            "- Do NOT invent data.\n"
            "- Do NOT compute new metrics.\n"
            "- Do NOT speculate beyond the provided facts.\n"
            "- Mention baseline confidence explicitly if it is LOW.\n"
            "- Do NOT recommend fixes unless a regression exists.\n"
            "- Maximum 4 sentences.\n"
        )

        # ---------------------------
        # Baseline section
        # ---------------------------
        if report.baseline_metrics:
            baseline_section = (
                f"- Baseline status: {report.baseline_metrics.overall_status}\n"
                f"- P95 latency delta: {report.baseline_metrics.latency_delta_pct}%\n"
                f"- Baseline confidence: {report.baseline_metrics.confidence}\n"
            )
        else:
            baseline_section = "- Baseline status: N/A\n"

        # ---------------------------
        # Infrastructure section
        # ---------------------------
        if report.infra_metrics:
            infra = report.infra_metrics
            infra_section = (
                f"- Server correlation status: {infra.status}\n"
                f"- Server throttled: {infra.server_throttled}\n"
                f"- Server saturated: {infra.server_saturated}\n"
                f"- Memory pressure: {infra.server_mem_pressure}\n"
                f"- Attribution: {infra.attribution_reason}\n"
            )
        else:
            infra_section = "- No server-side infrastructure correlation data available.\n"

        # ---------------------------
        # User prompt (FACTS ONLY)
        # ---------------------------
        user_prompt = f"""
Context:
- Environment: {report.context.environment}
- Load profile: {report.context.load_profile}
- APIs tested: {", ".join(report.context.apis)}

Overall assessment:
- Regression label: {report.regression_label}

Client-side performance:
- Average latency: {report.run_metrics.avg_ms} ms
- P95 latency: {report.run_metrics.p95_ms} ms
- Throughput: {report.run_metrics.throughput_rps} req/s
- Error rate: {report.run_metrics.error_rate_pct} %

Baseline comparison:
{baseline_section}

Infrastructure signals:
{infra_section}

Write a concise executive summary in bullet points in new line.
"""

        # ---------------------------
        # AI generation (fail-soft)
        # ---------------------------
        return self.llm.generate(system_prompt, user_prompt)