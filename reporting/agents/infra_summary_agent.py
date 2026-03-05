from reporting.models.report_model import ReportModel
from reporting.agents.local_llm_client import LocalLLMClient


class InfraSummaryAgent:
    """
    Generates a summary of server-side infrastructure correlation.
    Explanation only. No decisions.
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def run(self, report: ReportModel) -> str:
        # If run is invalid, do not explain
        if not report.is_valid:
            return "Infrastructure analysis is not available for an invalid run."

        # If no infra correlation data exists
        if not report.infra_metrics:
            return "No server-side infrastructure correlation data was available for this run."

        infra = report.infra_metrics

        # ---------------------------
        # System prompt
        # ---------------------------
        system_prompt = (
            "You are a performance analyst summarizing server-side correlation.\n"
            "Rules:\n"
            "- Write short, clear sentences.\n"
            "- One idea per sentence in bullet points. New line for every point.\n"
            "- Do NOT speculate beyond provided attribution.\n"
            "- State whether infrastructure is likely involved.\n"
            "- Be concise and factual.\n"
            "- Maximum 2 sentences.\n"
        )

        # ---------------------------
        # User prompt (facts only)
        # ---------------------------
        user_prompt = f"""
Server correlation status: {infra.status}

Infrastructure stress signals:
- Server throttled: {infra.server_throttled}
- Server saturated: {infra.server_saturated}
- Memory pressure: {infra.server_mem_pressure}

Attribution:
{infra.attribution_reason}

Write a concise infrastructure summary in bullet points in new line.
"""

        return self.llm.generate(system_prompt, user_prompt)