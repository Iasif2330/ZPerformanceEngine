from reporting.models.api_metrics import ApiMetrics
from reporting.models.report_model import ReportModel
from reporting.agents.local_llm_client import LocalLLMClient


class ApiSummaryAgent:
    """
    Generates a concise summary for a single API.
    Explanation only. No decisions.
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def run(self, api: ApiMetrics, report: ReportModel) -> str:
        # If run is invalid, do not explain
        if not report.is_valid:
            return "This API result is part of an invalid performance run."

        # ---------------------------
        # System prompt
        # ---------------------------
        system_prompt = (
            "You are a backend performance engineer.\n"
            "Rules:\n"
            "- Write short, clear sentences.\n"
            "- One idea per sentence in bullet points. New line for every point.\n"
            "- Focus only on API-level performance.\n"
            "- Do NOT speculate about causes.\n"
            "- Do NOT mention infrastructure metrics directly.\n"
            "- Be concise.\n"
            "- Maximum 2 sentences.\n"
        )

        # ---------------------------
        # Infrastructure context (high-level only)
        # ---------------------------
        infra_context = "No server-side correlation detected."
        if report.infra_metrics:
            infra_context = (
                f"Server correlation status: {report.infra_metrics.status}. "
                f"Execution-related factors may be involved."
            )

        # ---------------------------
        # User prompt (facts only)
        # ---------------------------
        user_prompt = f"""
API name: {api.api_name}

Metrics:
- P95 latency: {api.p95_ms} ms
- Error rate: {api.error_rate_pct} %

Context:
- Overall regression label: {report.regression_label}
- {infra_context}

Summarize this API's performance in bullet points in new line.
"""

        return self.llm.generate(system_prompt, user_prompt)