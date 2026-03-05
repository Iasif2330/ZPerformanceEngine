import subprocess


class LocalLLMClient:
    """
    Free local LLM client using Ollama.

    This implementation always uses the local `ollama` CLI.  If the binary is
    missing the `enabled` flag is set to False and generate() returns a
    diagnostic message rather than raising an exception.  The orchestrator is
    configured to always use this client regardless of environment variables.
    """

    def __init__(self, model: str = "mistral"):
        self.model = model
        import shutil
        self.enabled = shutil.which("ollama") is not None
        if not self.enabled:
            print("LocalLLMClient: 'ollama' binary not found, local AI disabled")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return text from local model or explanatory message.

        Parameters
        ----------
        system_prompt: str
            Instructions for the model.
        user_prompt: str
            The factual content to summarise.
        """

        prompt = f"{system_prompt}

{user_prompt}"

        if not self.enabled:
            return "[Local AI unavailable: ollama not installed]"

        try:
            result = subprocess.run(
                ["ollama", "run", self.model],
                input=prompt,
                text=True,
                capture_output=True,
                timeout=60,
            )
            text = result.stdout.strip()
            if not text:
                return "[Local AI returned no text]"
            return text
        except Exception as exc:
            return f"[Local AI error: {exc}]"