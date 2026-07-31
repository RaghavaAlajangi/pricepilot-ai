"""Deterministic three-agent LangGraph workflow.

    analyst  ->  strategist  ->  reviewer  ->  END

Each node is one LLM call with a *structured* output schema (Pydantic),
so downstream code never parses free text. The graph is intentionally
linear: for a pricing recommendation there is no branching decision an
LLM should make — determinism keeps latency, cost and audit trails
predictable.
"""

from typing import Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from ..schemas import (
    AnalystFindings,
    ReviewerVerdict,
    StrategistRecommendation,
)
from .llm_client import LLMClient
from .prompts import (
    ANALYST_PROMPT,
    REVIEWER_PROMPT,
    STRATEGIST_PROMPT,
)


class AgentState(TypedDict):
    """State threaded through the graph. ``payload`` is the ML result dict."""

    payload: dict
    analyst: Optional[AnalystFindings]
    strategist: Optional[StrategistRecommendation]
    reviewer: Optional[ReviewerVerdict]


def build_graph(llm: BaseChatModel):
    """Compile the linear analyst -> strategist -> reviewer graph."""
    client = LLMClient.from_llm(llm)

    def analyst_node(state: AgentState) -> dict:
        findings = client.call(
            ANALYST_PROMPT,
            {"model_results": state["payload"]},
            AnalystFindings,
        )
        return {"analyst": findings}

    def strategist_node(state: AgentState) -> dict:
        analyst = state["analyst"]
        assert analyst is not None  # linear graph guarantees order
        rec = client.call(
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
        verdict = client.call(
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


def run_workflow(payload: dict, llm: Optional[BaseChatModel] = None) -> AgentState:
    """Run the full workflow for one ML payload and return the final state."""
    compiled = build_graph(llm or LLMClient.from_settings()._llm)
    initial: AgentState = {
        "payload": payload,
        "analyst": None,
        "strategist": None,
        "reviewer": None,
    }
    return compiled.invoke(initial)
