import os
from reporting.orchestrator import ReportOrchestrator
from reporting.agents.llm_client import LLMClient
from reporting.agents.executive_agent import ExecutiveSummaryAgent
from reporting.agents.local_llm_client import LocalLLMClient

orch = ReportOrchestrator(os.getcwd())
report = orch.generate()

llm = LocalLLMClient(model="mistral")
agent = ExecutiveSummaryAgent(llm)

summary = agent.run(report)

print("\nEXECUTIVE SUMMARY:")
print(summary)