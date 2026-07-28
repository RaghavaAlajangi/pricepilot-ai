"""Deterministic three-agent LangGraph workflow.

    analyst  ->  strategist  ->  reviewer  ->  END

Each node is one LLM call with a *structured* output schema (Pydantic),
so downstream code never parses free text. The graph is intentionally
linear: for a pricing recommendation there is no branching decision an
LLM should make — determinism keeps latency, cost and audit trails
predictable.
"""

import json
from typing import Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agents.prompts import (
    ANALYST_PROMPT,
    REVIEWER_PROMPT,
    STRATEGIST_PROMPT,
)
from app.config import get_settings
from app.schemas import (
    AnalystFindings,
    ReviewerVerdict,
    StrategistRecommendation,
)

LLM_TEMPERATURE = 0.2  # low: we want consistent, factual analysis
LLM_MAX_TOKENS = 800


class AgentError(RuntimeError):
    """Raised when an LLM call fails; the API layer maps it to a 502."""


class AgentState(TypedDict):
    """State threaded through the graph. ``payload`` is the ML result dict."""

    payload: dict
    analyst: Optional[AnalystFindings]
    strategist: Optional[StrategistRecommendation]
    reviewer: Optional[ReviewerVerdict]


def build_llm() -> BaseChatModel:
    """One chat model instance shared by all nodes."""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        timeout=60,
        max_retries=2,
    )


def _call(
    llm: BaseChatModel, system_prompt: str, user_content: dict, schema: type
):
    """Single structured LLM call; wraps provider errors into AgentError."""
    try:
        structured = llm.with_structured_output(schema)
        return structured.invoke(
            [
                ("system", system_prompt),
                ("user", json.dumps(user_content, default=str)),
            ]
        )
    except Exception as exc:  # provider/network errors -> friendly failure
        raise AgentError(
            f"{schema.__name__} agent call failed: {exc}"
        ) from exc


def build_graph(llm: BaseChatModel):
    """Compile the linear analyst -> strategist -> reviewer graph."""

    def analyst_node(state: AgentState) -> dict:
        findings = _call(
            llm,
            ANALYST_PROMPT,
            {"model_results": state["payload"]},
            AnalystFindings,
        )
        return {"analyst": findings}

    def strategist_node(state: AgentState) -> dict:
        analyst = state["analyst"]
        assert analyst is not None  # linear graph guarantees order
        rec = _call(
            llm,
            STRATEGIST_PROMPT,
            {
                "model_results": state["payload"],
                "analyst_findings": analyst.model_dump(),
            },
            StrategistRecommendation,
        )
        return {"strategist": rec}

    def reviewer_node(state: AgentState) -> dict:
        analyst, strategist = state["analyst"], state["strategist"]
        assert analyst is not None and strategist is not None
        verdict = _call(
            llm,
            REVIEWER_PROMPT,
            {
                "model_results": state["payload"],
                "analyst_findings": analyst.model_dump(),
                "strategist_recommendation": strategist.model_dump(),
            },
            ReviewerVerdict,
        )
        return {"reviewer": verdict}

    # node names must differ from state keys, hence the _agent suffix
    graph = StateGraph(AgentState)
    graph.add_node("analyst_agent", analyst_node)
    graph.add_node("strategist_agent", strategist_node)
    graph.add_node("reviewer_agent", reviewer_node)
    graph.add_edge(START, "analyst_agent")
    graph.add_edge("analyst_agent", "strategist_agent")
    graph.add_edge("strategist_agent", "reviewer_agent")
    graph.add_edge("reviewer_agent", END)
    return graph.compile()


def run_workflow(
    payload: dict, llm: Optional[BaseChatModel] = None
) -> AgentState:
    """Run the full workflow for one ML payload and return the final state."""
    compiled = build_graph(llm or build_llm())
    initial: AgentState = {
        "payload": payload,
        "analyst": None,
        "strategist": None,
        "reviewer": None,
    }
    return compiled.invoke(initial)
