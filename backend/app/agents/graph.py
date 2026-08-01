"""Deterministic three-agent LangGraph workflow.

    analyst  ->  strategist  ->  reviewer  ->  END

Each node is one LLM call with a *structured* output schema (Pydantic),
so downstream code never parses free text. The graph is intentionally
linear: for a pricing recommendation there is no branching decision an
LLM should make — determinism keeps latency, cost and audit trails
predictable.

Every node also records an ``AgentStepStats`` entry (latency + token
usage) into the shared state so the API can expose per-step telemetry.
"""

from typing import Iterator, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from ..schemas import (
    AgentStepStats,
    AnalystFindings,
    ReviewerVerdict,
    StrategistRecommendation,
)
from .llm_client import LLMCallResult, LLMClient
from .prompts import (
    ANALYST_PROMPT,
    REVIEWER_PROMPT,
    STRATEGIST_PROMPT,
)

# Execution order of the graph nodes; the stream endpoint relies on it.
AGENT_SEQUENCE: tuple[str, ...] = ("analyst", "strategist", "reviewer")


class AgentState(TypedDict):
    """State threaded through the graph. ``payload`` is the ML result dict."""

    payload: dict
    analyst: Optional[AnalystFindings]
    strategist: Optional[StrategistRecommendation]
    reviewer: Optional[ReviewerVerdict]
    steps: list[AgentStepStats]


def _step(agent: str, call: LLMCallResult) -> AgentStepStats:
    return AgentStepStats(
        agent=agent,  # type: ignore[arg-type]  # agent comes from AGENT_SEQUENCE
        latency_ms=call.latency_ms,
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
    )


def build_graph(llm: BaseChatModel):
    """Compile the linear analyst -> strategist -> reviewer graph."""
    client = LLMClient.from_llm(llm)

    def analyst_node(state: AgentState) -> dict:
        call = client.call(
            ANALYST_PROMPT,
            {"model_results": state["payload"]},
            AnalystFindings,
        )
        return {
            "analyst": call.output,
            "steps": state["steps"] + [_step("analyst", call)],
        }

    def strategist_node(state: AgentState) -> dict:
        analyst = state["analyst"]
        assert analyst is not None  # linear graph guarantees order
        call = client.call(
            STRATEGIST_PROMPT,
            {
                "model_results": state["payload"],
                "analyst_findings": analyst.model_dump(),
            },
            StrategistRecommendation,
        )
        return {
            "strategist": call.output,
            "steps": state["steps"] + [_step("strategist", call)],
        }

    def reviewer_node(state: AgentState) -> dict:
        analyst, strategist = state["analyst"], state["strategist"]
        assert analyst is not None and strategist is not None
        call = client.call(
            REVIEWER_PROMPT,
            {
                "model_results": state["payload"],
                "analyst_findings": analyst.model_dump(),
                "strategist_recommendation": strategist.model_dump(),
            },
            ReviewerVerdict,
        )
        return {
            "reviewer": call.output,
            "steps": state["steps"] + [_step("reviewer", call)],
        }

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


def _initial_state(payload: dict) -> AgentState:
    return {
        "payload": payload,
        "analyst": None,
        "strategist": None,
        "reviewer": None,
        "steps": [],
    }


def run_workflow(payload: dict, llm: Optional[BaseChatModel] = None) -> AgentState:
    """Run the full workflow for one ML payload and return the final state."""
    compiled = build_graph(llm or LLMClient.from_settings()._llm)
    return compiled.invoke(_initial_state(payload))


def stream_workflow(
    payload: dict, llm: Optional[BaseChatModel] = None
) -> Iterator[tuple[str, AgentState]]:
    """Yield ``(agent_name, merged_state)`` after each node completes."""
    compiled = build_graph(llm or LLMClient.from_settings()._llm)
    state: AgentState = _initial_state(payload)
    for update in compiled.stream(state, stream_mode="updates"):
        # updates look like {"analyst_agent": {"analyst": ..., "steps": [...]}}
        node_name, node_update = next(iter(update.items()))
        state = {**state, **node_update}  # type: ignore[typeddict-item]
        yield node_name.removesuffix("_agent"), state
