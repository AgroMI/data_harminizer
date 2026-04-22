from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from backend.app.llm.config import LocalLLMConfig


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    success: bool
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    content: str | None
    error_code: str | None = None
    error_message: str | None = None


class LocalLLMClient:
    def __init__(self, config: LocalLLMConfig) -> None:
        self._config = config

    def chat_completion(self, *, messages: list[dict[str, str]]) -> LLMCallResult:
        payload = {
            "model": self._config.model_name,
            "messages": messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_output_tokens,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        http_request = request.Request(
            self._config.endpoint,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self._config.timeout_ms / 1000.0) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            return LLMCallResult(
                success=False,
                request_payload=payload,
                response_payload={"raw": raw, "status": exc.code},
                content=None,
                error_code="http_error",
                error_message=f"Local LLM HTTP error {exc.code}",
            )
        except error.URLError as exc:
            return LLMCallResult(
                success=False,
                request_payload=payload,
                response_payload={},
                content=None,
                error_code="connection_error",
                error_message=str(exc.reason),
            )
        except TimeoutError:
            return LLMCallResult(
                success=False,
                request_payload=payload,
                response_payload={},
                content=None,
                error_code="timeout",
                error_message="Local LLM request timed out.",
            )

        try:
            response_payload = json.loads(raw)
        except json.JSONDecodeError:
            return LLMCallResult(
                success=False,
                request_payload=payload,
                response_payload={"raw": raw},
                content=None,
                error_code="invalid_json_response",
                error_message="Local LLM response was not valid JSON.",
            )

        content = _extract_chat_content(response_payload)
        if content is None:
            return LLMCallResult(
                success=False,
                request_payload=payload,
                response_payload=response_payload,
                content=None,
                error_code="missing_content",
                error_message="Local LLM response did not include assistant content.",
            )

        return LLMCallResult(
            success=True,
            request_payload=payload,
            response_payload=response_payload,
            content=content,
        )


def _extract_chat_content(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    return None
