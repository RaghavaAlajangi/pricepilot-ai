"""LLM client: construction and structured invocation."""

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from ..config import get_settings

LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 800


class AgentError(RuntimeError):
    """Raised when an LLM call fails; the API layer maps it to a 502."""


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

    def call(self, system_prompt: str, user_content: dict, schema: type) -> Any:
        """Single LLM call; wraps provider errors into AgentError."""
        try:
            structured = self._llm.with_structured_output(schema)
            return structured.invoke(
                [
                    ("system", system_prompt),
                    ("user", json.dumps(user_content, default=str)),
                ]
            )
        except Exception as exc:
            raise AgentError(f"{schema.__name__} agent call failed: {exc}") from exc
