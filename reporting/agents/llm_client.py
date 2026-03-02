# reporting/agents/llm_client.py
import os
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class LLMClient:
    """
    Safe, bounded LLM client.
    AI is explanatory only.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int = 400,
        timeout: int = 20,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        self.enabled = (
            OpenAI is not None and
            os.getenv("OPENAI_API_KEY") is not None
        )

        self.client: Optional[OpenAI] = OpenAI() if self.enabled else None

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.enabled:
            return "[AI disabled]"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )

        return response.choices[0].message.content.strip()