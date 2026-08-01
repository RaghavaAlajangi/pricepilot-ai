"""LLM client: construction and structured invocation with telemetry."""

import json
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from ..config import get_settings

LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 800


class AgentError(RuntimeError):
    """Raised when an LLM call fails; the API layer maps it to a 502."""


@dataclass(frozen=True)
class LLMCallResult:
    """One structured LLM call: parsed output plus telemetry."""

    output: Any
    latency_ms: int
    input_tokens: int
    output_tokens: int


class LLMClient:
    """Wraps a chat model with structured output and error handling."""

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    @classmethod
    def from_settings(cls) -> "LLMClient":
        settings = get_settings()
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            timeout=60,
            max_retries=2,
        )
        return cls(llm)

    @classmethod
    def from_llm(cls, llm: BaseChatModel) -> "LLMClient":
        return cls(llm)

    def call(
        self, system_prompt: str, user_content: dict, schema: type
    ) -> LLMCallResult:
        """Single LLM call; wraps provider errors into AgentError.

        ``include_raw=True`` keeps the raw AIMessage alongside the parsed
        object so token usage can be reported per agent step.
        """
        try:
            structured = self._llm.with_structured_output(schema, include_raw=True)
            started = time.perf_counter()
            result = structured.invoke(
                [
                    ("system", system_prompt),
                    ("user", json.dumps(user_content, default=str)),
                ]
            )
            latency_ms = round((time.perf_counter() - started) * 1000)
        except Exception as exc:
            raise AgentError(f"{schema.__name__} agent call failed: {exc}") from exc
        if result.get("parsing_error") or result.get("parsed") is None:
            raise AgentError(
                f"{schema.__name__} agent returned unparseable output: "
                f"{result.get('parsing_error')}"
            )
        usage = getattr(result.get("raw"), "usage_metadata", None) or {}
        return LLMCallResult(
            output=result["parsed"],
            latency_ms=latency_ms,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )
