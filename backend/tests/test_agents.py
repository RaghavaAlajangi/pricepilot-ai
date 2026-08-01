"""Agent workflow with a fake LLM: verifies graph wiring, node order and
per-step telemetry."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.graph import AGENT_SEQUENCE, run_workflow, stream_workflow
from app.schemas import (
    AnalystFindings,
    ReviewerVerdict,
    StrategistRecommendation,
)

pytestmark = pytest.mark.agent

FAKE_OUTPUTS: dict[type, Any] = {
    AnalystFindings: AnalystFindings(
        summary="Demand is price-sensitive.",
        findings=["Elasticity is -1.8", "Fit R² is 0.6"],
        data_quality_notes=["Only 90 weeks of data"],
    ),
    StrategistRecommendation: StrategistRecommendation(
        recommended_price_eur=84.5,
        rationale="Close to the model optimum.",
        expected_impact="Slightly higher weekly profit.",
        risks=["Competitor undercut"],
    ),
    ReviewerVerdict: ReviewerVerdict(
        verdict="approve", checks_performed=["above cost"], concerns=[]
    ),
}
FAKE_USAGE = {"input_tokens": 500, "output_tokens": 120, "total_tokens": 620}


class FakeStructuredLLM:
    """Stands in for ChatOpenAI: returns canned objects per output schema.

    Mirrors ``with_structured_output(schema, include_raw=True)``: invoke
    returns ``{"raw": <message with usage_metadata>, "parsed": <object>,
    "parsing_error": None}``.
    """

    def __init__(self) -> None:
        self.calls: list[type] = []

    def with_structured_output(
        self, schema: type, include_raw: bool = False
    ) -> "FakeStructuredLLM":
        assert include_raw, "LLMClient must request the raw message for telemetry"
        self._schema = schema
        return self

    def invoke(self, messages: list) -> dict:
        self.calls.append(self._schema)
        return {
            "raw": SimpleNamespace(usage_metadata=FAKE_USAGE),
            "parsed": FAKE_OUTPUTS[self._schema],
            "parsing_error": None,
        }


def test_workflow_runs_all_three_agents_in_order() -> None:
    llm = FakeStructuredLLM()
    state = run_workflow({"elasticity": -1.8, "current_price_eur": 80.0}, llm=llm)

    assert llm.calls == [
        AnalystFindings,
        StrategistRecommendation,
        ReviewerVerdict,
    ]
    assert state["analyst"] == FAKE_OUTPUTS[AnalystFindings]
    assert state["strategist"].recommended_price_eur == 84.5
    assert state["reviewer"].verdict == "approve"


def test_workflow_records_one_telemetry_step_per_agent() -> None:
    state = run_workflow({"elasticity": -1.8}, llm=FakeStructuredLLM())

    assert [s.agent for s in state["steps"]] == list(AGENT_SEQUENCE)
    for step in state["steps"]:
        assert step.input_tokens == FAKE_USAGE["input_tokens"]
        assert step.output_tokens == FAKE_USAGE["output_tokens"]
        assert step.latency_ms >= 0


def test_stream_workflow_yields_agents_in_order() -> None:
    events = list(stream_workflow({"elasticity": -1.8}, llm=FakeStructuredLLM()))

    assert [agent for agent, _ in events] == list(AGENT_SEQUENCE)
    # state accumulates: one step after the analyst, three after the reviewer
    assert len(events[0][1]["steps"]) == 1
    assert len(events[-1][1]["steps"]) == 3
    assert events[-1][1]["reviewer"].verdict == "approve"
