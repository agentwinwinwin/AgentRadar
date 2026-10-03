from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings


class LLMError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class LLMResult:
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...

    def complete_stream(
        self,
        messages: list[dict[str, str]],
        *,
        response_schema: dict[str, Any] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> LLMResult: ...


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        timeout: int,
        max_output_tokens: int,
        temperature: float,
    ) -> None:
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        request_messages = list(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
        }
        if response_schema:
            if self.provider == "deepseek":
                payload["response_format"] = {"type": "json_object"}
                request_messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "Return one JSON object matching this schema exactly: "
                            + json.dumps(response_schema, separators=(",", ":"))
                        ),
                    },
                )
            else:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "agentradar_response",
                        "strict": True,
                        "schema": response_schema,
                    },
                }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError("LLM_UNAVAILABLE", "Configured LLM provider is unavailable.") from exc
        try:
            usage = result.get("usage") or {}
            return LLMResult(
                result["choices"][0]["message"]["content"],
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "LLM_INVALID_RESPONSE", "LLM provider returned an invalid response."
            ) from exc

    def complete_stream(
        self,
        messages: list[dict[str, str]],
        *,
        response_schema: dict[str, Any] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> LLMResult:
        request_messages = list(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if response_schema:
            if self.provider == "deepseek":
                payload["response_format"] = {"type": "json_object"}
                request_messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "Return one JSON object matching this schema exactly: "
                            + json.dumps(response_schema, separators=(",", ":"))
                        ),
                    },
                )
            else:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "agentradar_response",
                        "strict": True,
                        "schema": response_schema,
                    },
                }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        chunks: list[str] = []
        usage: dict[str, Any] = {}
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    usage = event.get("usage") or usage
                    choices = event.get("choices") or []
                    delta = choices[0].get("delta", {}).get("content") if choices else None
                    if isinstance(delta, str) and delta:
                        chunks.append(delta)
                        if on_delta:
                            on_delta(delta)
        except (
            urllib.error.URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise LLMError("LLM_UNAVAILABLE", "Configured LLM provider is unavailable.") from exc
        content = "".join(chunks)
        if not content:
            raise LLMError("LLM_INVALID_RESPONSE", "LLM provider returned an invalid response.")
        return LLMResult(
            content,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )


class OpenAIResponsesClient(OpenAICompatibleClient):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": messages,
            "max_output_tokens": self.max_output_tokens,
        }
        if response_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "agentradar_response",
                    "strict": True,
                    "schema": response_schema,
                }
            }
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError("LLM_UNAVAILABLE", "Configured LLM provider is unavailable.") from exc
        content = result.get("output_text") or self._output_text(result)
        if not isinstance(content, str) or not content:
            raise LLMError("LLM_INVALID_RESPONSE", "LLM provider returned an invalid response.")
        usage = result.get("usage") or {}
        return LLMResult(content, usage.get("input_tokens"), usage.get("output_tokens"))

    @staticmethod
    def _output_text(result: dict[str, Any]) -> str | None:
        for output in result.get("output", []):
            for item in output.get("content", []):
                if item.get("type") == "output_text":
                    return item.get("text")
        return None


def llm_client() -> LLMClient:
    if not settings.LLM_PROVIDER or not settings.LLM_MODEL or not settings.LLM_API_KEY:
        raise LLMError("LLM_NOT_CONFIGURED", "A real LLM provider is not configured.")
    if settings.LLM_PROVIDER not in {"openai", "openai_compatible", "deepseek"}:
        raise LLMError("LLM_PROVIDER_UNSUPPORTED", "Configured LLM provider is unsupported.")
    client_class = (
        OpenAIResponsesClient if settings.LLM_PROVIDER == "openai" else OpenAICompatibleClient
    )
    return client_class(
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        temperature=settings.LLM_TEMPERATURE,
    )
