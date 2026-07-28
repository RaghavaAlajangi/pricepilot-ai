"""Agent workflow with a fake LLM: verifies graph wiring and node order."""

from typing import Any

from app.agents.graph import run_workflow
from app.schemas import (
    AnalystFindings,
    ReviewerVerdict,
    StrategistRecommendation,
)

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


class FakeStructuredLLM:
    """Stands in for ChatOpenAI: returns canned objects per output schema."""

    def __init__(self) -> None:
        self.calls: list[type] = []

    def with_structured_output(self, schema: type) -> "FakeStructuredLLM":
        self._schema = schema
        return self

    def invoke(self, messages: list) -> Any:
        self.calls.append(self._schema)
        return FAKE_OUTPUTS[self._schema]


def test_workflow_runs_all_three_agents_in_order() -> None:
    llm = FakeStructuredLLM()
    state = run_workflow(
        {"elasticity": -1.8, "current_price_eur": 80.0}, llm=llm
    )

    assert llm.calls == [
        AnalystFindings,
        StrategistRecommendation,
        ReviewerVerdict,
    ]
    assert state["analyst"] == FAKE_OUTPUTS[AnalystFindings]
    assert state["strategist"].recommended_price_eur == 84.5
    assert state["reviewer"].verdict == "approve"
