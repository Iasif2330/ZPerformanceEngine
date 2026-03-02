import os
from reporting.orchestrator import ReportOrchestrator
from reporting.agents.llm_client import LLMClient
from reporting.agents.api_summary_agent import ApiSummaryAgent
from reporting.agents.local_llm_client import LocalLLMClient

orch = ReportOrchestrator(os.getcwd())
report = orch.generate()

llm = LocalLLMClient(model="mistral")
agent = ApiSummaryAgent(llm)

for api in report.api_metrics:
    summary = agent.run(api, report)
    print(f"\nAPI: {api.api_name}")
    print("SUMMARY:", summary)