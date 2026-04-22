import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocalLLMConfig:
    enabled: bool
    hybrid_enabled: bool
    tool_orchestration_enabled: bool
    endpoint: str
    model_name: str
    api_key: str | None
    timeout_ms: int
    max_output_tokens: int
    temperature: float

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.endpoint.strip()) and bool(self.model_name.strip())


def load_local_llm_config() -> LocalLLMConfig:
    return LocalLLMConfig(
        enabled=_env_bool("LOCAL_LLM_ENABLED", False),
        hybrid_enabled=_env_bool("LOCAL_LLM_HYBRID_ENABLED", False),
        tool_orchestration_enabled=_env_bool("LOCAL_LLM_TOOL_ORCHESTRATION_ENABLED", False),
        endpoint=os.getenv("LOCAL_LLM_ENDPOINT", "http://localhost:11434/v1/chat/completions").strip(),
        model_name=os.getenv("LOCAL_LLM_MODEL", "").strip(),
        api_key=os.getenv("LOCAL_LLM_API_KEY", "").strip() or None,
        timeout_ms=_env_int("LOCAL_LLM_TIMEOUT_MS", 12000),
        max_output_tokens=_env_int("LOCAL_LLM_MAX_OUTPUT_TOKENS", 900),
        temperature=_env_float("LOCAL_LLM_TEMPERATURE", 0.0),
    )


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
