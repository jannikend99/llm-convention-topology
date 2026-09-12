"""LLM client: localhost OpenAI-compat or mock. JSON enum only."""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable
from urllib.parse import urlparse

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, OpenAI, RateLimitError

from convention_topology.config import ConfigError, is_localhost_url
from convention_topology.json_output import ParseError, json_schema_for_options, parse_decision


class RunFailedError(Exception):
    def __init__(self, message: str, error_class: str = "attempts_exhausted"):
        super().__init__(message)
        self.error_class = error_class


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: dict
    model_id: str
    finish_reason: str | None = None
    http_status: int | None = 200
    reasoning: str | None = None
    error_class: str | None = None


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, prompt: str, *, options: Sequence[str]) -> LLMResponse: ...


@runtime_checkable
class AsyncLLMClient(Protocol):
    async def complete(self, prompt: str, *, options: Sequence[str]) -> LLMResponse: ...


DEFAULT_REQUEST_TIMEOUT = 120.0
THINKING_REQUEST_TIMEOUT = 300.0


def request_timeout(*, thinking: bool) -> float:
    return THINKING_REQUEST_TIMEOUT if thinking else DEFAULT_REQUEST_TIMEOUT


def openai_extra_body(
    *,
    thinking: bool,
    reasoning_effort: str | None,
    thinking_token_budget: int | None = None,
) -> dict[str, Any]:
    extra: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": thinking}}
    if reasoning_effort:
        extra["reasoning_effort"] = reasoning_effort
    if thinking_token_budget is not None:
        extra["thinking_token_budget"] = int(thinking_token_budget)
    return extra


def chat_completion_kwargs(
    *,
    model_id: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    options: Sequence[str],
    json_schema: bool,
    thinking: bool,
    reasoning_effort: str | None,
    send_chat_template_kwargs: bool,
    thinking_token_budget: int | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_schema:
        kwargs["response_format"] = json_schema_for_options(options)
    if send_chat_template_kwargs:
        kwargs["extra_body"] = openai_extra_body(
            thinking=thinking,
            reasoning_effort=reasoning_effort,
            thinking_token_budget=thinking_token_budget,
        )
    return kwargs


def _require_localhost(base_url: str, provider: str) -> None:
    if provider == "mock":
        return
    if not is_localhost_url(base_url):
        raise ConfigError("non-localhost base_url fails unless provider is mock")


class OpenAICompatClient:
    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_key: str = "EMPTY",
        temperature: float = 0.5,
        max_tokens: int = 512,
        timeout: float | None = None,
        provider: str = "openai_compat",
        reasoning_effort: str | None = None,
        thinking: bool = False,
        json_schema: bool = True,
        send_chat_template_kwargs: bool = True,
        thinking_token_budget: int | None = None,
    ):
        _require_localhost(base_url, provider)
        resolved_timeout = request_timeout(thinking=thinking) if timeout is None else timeout
        self._client = OpenAI(
            api_key=api_key or "EMPTY",
            base_url=base_url.rstrip("/") + "/",
            max_retries=0,
            timeout=resolved_timeout,
        )
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.reasoning_effort = reasoning_effort
        self.thinking = thinking
        self.json_schema = json_schema
        self.send_chat_template_kwargs = send_chat_template_kwargs
        self.thinking_token_budget = thinking_token_budget
        self.timeout = resolved_timeout

    def complete(self, prompt: str, *, options: Sequence[str]) -> LLMResponse:
        kwargs = chat_completion_kwargs(
            model_id=self.model_id,
            prompt=prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            options=options,
            json_schema=self.json_schema,
            thinking=self.thinking,
            reasoning_effort=self.reasoning_effort,
            send_chat_template_kwargs=self.send_chat_template_kwargs,
            thinking_token_budget=self.thinking_token_budget,
        )
        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        text = message.content or ""
        usage = getattr(response, "usage", None)
        reasoning = getattr(message, "reasoning", None)
        finish = getattr(response.choices[0], "finish_reason", None)
        return LLMResponse(
            text=text,
            usage=(
                {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "reasoning_tokens": getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
                    if usage
                    else None,
                }
                if usage
                else {}
            ),
            model_id=self.model_id,
            finish_reason=finish,
            reasoning=reasoning,
        )


class AsyncOpenAICompatClient:
    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_key: str = "EMPTY",
        temperature: float = 0.5,
        max_tokens: int = 512,
        timeout: float | None = None,
        provider: str = "openai_compat",
        reasoning_effort: str | None = None,
        thinking: bool = False,
        json_schema: bool = True,
        send_chat_template_kwargs: bool = True,
        thinking_token_budget: int | None = None,
    ):
        _require_localhost(base_url, provider)
        resolved_timeout = request_timeout(thinking=thinking) if timeout is None else timeout
        self._client = AsyncOpenAI(
            api_key=api_key or "EMPTY",
            base_url=base_url.rstrip("/") + "/",
            max_retries=0,
            timeout=resolved_timeout,
        )
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.reasoning_effort = reasoning_effort
        self.thinking = thinking
        self.json_schema = json_schema
        self.send_chat_template_kwargs = send_chat_template_kwargs
        self.thinking_token_budget = thinking_token_budget
        self.timeout = resolved_timeout

    async def complete(self, prompt: str, *, options: Sequence[str]) -> LLMResponse:
        kwargs = chat_completion_kwargs(
            model_id=self.model_id,
            prompt=prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            options=options,
            json_schema=self.json_schema,
            thinking=self.thinking,
            reasoning_effort=self.reasoning_effort,
            send_chat_template_kwargs=self.send_chat_template_kwargs,
            thinking_token_budget=self.thinking_token_budget,
        )
        response = await self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        text = message.content or ""
        usage = getattr(response, "usage", None)
        reasoning = getattr(message, "reasoning", None)
        finish = getattr(response.choices[0], "finish_reason", None)
        return LLMResponse(
            text=text,
            usage=(
                {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "reasoning_tokens": getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
                    if usage
                    else None,
                }
                if usage
                else {}
            ),
            model_id=self.model_id,
            finish_reason=finish,
            reasoning=reasoning,
        )


_PARTNER_RE = re.compile(r"Player 2=([^,\s]+)")


@dataclass
class MockLLMClient:
    policy: str
    rng: random.Random
    options: Sequence[str] | None = None
    scripted_responses: Sequence[str] = field(default_factory=tuple)
    always_label: str | None = None
    model_id: str = "mock"
    call_count: int = field(default=0, init=False)
    _scripted_index: int = field(default=0, init=False)

    def complete(self, prompt: str, *, options: Sequence[str] | None = None) -> LLMResponse:
        self.call_count += 1
        enum = list(options if options is not None else self.options or [])
        if self.policy == "scripted":
            text = self._next_scripted()
        elif self.policy == "always":
            text = self._format_response(self.always_label)
        elif self.policy == "imitate_modal":
            text = self._format_response(self._imitate_modal(prompt, enum))
        elif self.policy == "random":
            text = self._format_response(self.rng.choice(enum))
        else:
            raise ValueError(f"Unknown mock policy: {self.policy}")
        return LLMResponse(text=text, usage={"prompt_tokens": 0, "completion_tokens": 0}, model_id=self.model_id)

    def _next_scripted(self) -> str:
        if not self.scripted_responses:
            raise RuntimeError("scripted policy requires scripted_responses")
        text = self.scripted_responses[self._scripted_index % len(self.scripted_responses)]
        self._scripted_index += 1
        return text

    def _imitate_modal(self, prompt: str, enum: Sequence[str]) -> str:
        partner_answers = _PARTNER_RE.findall(prompt)
        if not partner_answers:
            return self.rng.choice(list(enum))
        return Counter(partner_answers).most_common(1)[0][0]

    @staticmethod
    def _format_response(label: str | None) -> str:
        return json.dumps({"value": label, "reason": "mock"}, separators=(",", ":"))


@dataclass
class AsyncClientAdapter:
    inner: MockLLMClient

    @property
    def call_count(self) -> int:
        return self.inner.call_count

    async def complete(self, prompt: str, *, options: Sequence[str] | None = None) -> LLMResponse:
        return self.inner.complete(prompt, options=options)


OPENAI_RETRY_EXCEPTIONS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIError,
    ParseError,
)


def classify_error(exc: BaseException) -> str:
    if isinstance(exc, ParseError):
        return "invalid_json" if "JSON" in str(exc) else "schema"
    if isinstance(exc, APITimeoutError):
        return "timeout"
    if isinstance(exc, (APIConnectionError, ConnectionError, OSError)):
        return "transport"
    if isinstance(exc, (APIError, RateLimitError)):
        return "http"
    message = str(exc).lower()
    if "truncat" in message:
        return "truncated"
    return "schema"


def error_raw(exc: BaseException) -> str:
    if isinstance(exc, ParseError):
        return ""
    body = getattr(exc, "body", None)
    if body is not None:
        return str(body)[:4000]
    return str(exc)[:4000]
