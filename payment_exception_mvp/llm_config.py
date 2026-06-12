from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "gpt-5.4"
DEFAULT_SUBAGENT_MODEL = "gpt-5.4-mini"


def load_dotenv(path: str | os.PathLike[str] | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ without overriding existing vars.

    Zero-dependency: real environment variables always win, so this is safe in CI/containers.
    Looks for a .env at the repo root by default.
    """
    env_path = Path(path) if path else Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # A blank value in .env means "unset" — do not write an empty string into the
        # environment, or SDKs that read e.g. OPENAI_BASE_URL would get a malformed value.
        if key and value and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class LLMConfig:
    """Runtime configuration for the OpenAI-backed final decision stage.

    The orchestrator stays runnable without any network access: when the API key
    is absent (or the SDK is unavailable) the deterministic decision is used as-is.
    """

    enabled: bool
    api_key: str | None
    model: str
    base_url: str | None
    max_tool_iterations: int
    temperature: float | None
    subagent_model: str = DEFAULT_SUBAGENT_MODEL

    @classmethod
    def from_env(cls) -> "LLMConfig":
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        disabled = os.getenv("PAYMENT_EXCEPTION_DISABLE_LLM", "").lower() in {"1", "true", "yes"}
        temperature_raw = os.getenv("OPENAI_TEMPERATURE")
        return cls(
            enabled=bool(api_key) and not disabled,
            api_key=api_key,
            model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            max_tool_iterations=int(os.getenv("OPENAI_MAX_TOOL_ITERATIONS", "8")),
            temperature=float(temperature_raw) if temperature_raw else None,
            subagent_model=os.getenv("OPENAI_SUBAGENT_MODEL", DEFAULT_SUBAGENT_MODEL),
        )
