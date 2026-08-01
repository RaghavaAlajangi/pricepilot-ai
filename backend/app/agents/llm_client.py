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
# Total attempts when the model returns schema-invalid output (transport
# errors are retried separately via the client's max_retries).
LLM_PARSE_ATTEMPTS = 2


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
        """Structured LLM call; wraps provider errors into AgentError.

        ``include_raw=True`` keeps the raw AIMessage alongside the parsed
        object so token usage can be reported per agent step. Transport
        errors are retried by the underlying client (``max_retries``);
        schema-parse failures are nondeterministic, so one re-invoke is
        attempted before giving up.
        """
        structured = self._llm.with_structured_output(schema, include_raw=True)
        messages = [
            ("system", system_prompt),
            ("user", json.dumps(user_content, default=str)),
        ]
        started = time.perf_counter()
        parse_error: object = None
        for _ in range(LLM_PARSE_ATTEMPTS):
            try:
                result = structured.invoke(messages)
            except Exception as exc:
                raise AgentError(
                    f"{schema.__name__} agent call failed: {exc}"
                ) from exc
            if not result.get("parsing_error") and result.get("parsed") is not None:
                usage = getattr(result.get("raw"), "usage_metadata", None) or {}
                return LLMCallResult(
                    output=result["parsed"],
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    input_tokens=int(usage.get("input_tokens", 0)),
                    output_tokens=int(usage.get("output_tokens", 0)),
                )
            parse_error = result.get("parsing_error")
        raise AgentError(
            f"{schema.__name__} agent returned unparseable output: {parse_error}"
        )
