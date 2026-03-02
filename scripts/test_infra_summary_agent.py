import os
from reporting.orchestrator import ReportOrchestrator
from reporting.agents.llm_client import LLMClient
from reporting.agents.infra_summary_agent import InfraSummaryAgent
from reporting.agents.local_llm_client import LocalLLMClient

orch = ReportOrchestrator(os.getcwd())
report = orch.generate()

llm = LocalLLMClient(model="mistral")
agent = InfraSummaryAgent(llm)

summary = agent.run(report)

print("\nINFRA SUMMARY:")
print(summary)