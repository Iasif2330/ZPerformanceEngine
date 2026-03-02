import subprocess


class LocalLLMClient:
    """
    Free local LLM client using Ollama.
    """

    def __init__(self, model: str = "mistral"):
        self.model = model
        self.enabled = True

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            result = subprocess.run(
                ["ollama", "run", self.model],
                input=prompt,
                text=True,
                capture_output=True,
                timeout=60,
            )
            return result.stdout.strip()
        except Exception:
            return "[Local AI unavailable]"