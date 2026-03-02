from reporting.agents.llm_client import LLMClient
from reporting.agents.local_llm_client import LocalLLMClient


llm = LocalLLMClient(model="mistral")

output = llm.generate(
    system_prompt="You are a test system.",
    user_prompt="Say hello."
)

print("LLM OUTPUT:", output)