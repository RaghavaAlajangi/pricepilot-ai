"""Agent evaluation tests: structure, grounding, safety, and consistency checks.

These tests mirror the checks in scripts/evaluate_agents.py but run under
pytest so they are part of the standard test suite and CI pipeline.

Each case runs in OFFLINE mode (simulated agent output) so no API key is
required.  The ``inject_bad`` parametrize variant proves the checks fire on
deliberately unsafe output.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.guardrails import ungrounded_numbers, validate_recommendation
from app.schemas import (
    AgentAnalysisResponse,
    AnalystFindings,
    GuardrailReport,
    ReviewerVerdict,
    StrategistRecommendation,
)
from app.services import pricing

pytestmark = pytest.mark.agent

# ---------------------------------------------------------------------------
# Cases: (product_id, market)
# ---------------------------------------------------------------------------
EXAMPLE_CASES = [("SKU-1000", "DE"), ("SKU-1010", "FR"), ("SKU-1020", "CH")]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_dataset(tmp_path: Path) -> Path:
    """Write a synthetic multi-SKU / multi-market CSV and return its path."""
    rng = np.random.default_rng(42)
    rows: list[dict[str, Any]] = []
    sku_market = [
        ("SKU-1000", "DE", "Pendant Light A", "Pendant Lights"),
        ("SKU-1010", "FR", "Floor Lamp B", "Floor Lamps"),
        ("SKU-1020", "CH", "Table Lamp C", "Table Lamps"),
    ]
    price_levels = np.array([69.95, 79.95, 89.95, 99.95])
    elasticity = -2.0
    n_days = 364
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")

    for product_id, market, name, category in sku_market:
        prices = price_levels[(np.arange(n_days) // 28) % len(price_levels)]
        demand = 40_000.0 * prices**elasticity
        units = rng.poisson(demand)
        for i, date in enumerate(dates):
            rows.append(
                {
                    "date": date.date(),
                    "product_id": product_id,
                    "product_name": name,
                    "category": category,
                    "brand": "Casaluce",
                    "market": market,
                    "unit_price_eur": prices[i],
                    "unit_cost_eur": 40.0,
                    "units_sold": int(units[i]),
                    "web_sessions": int(rng.integers(20, 120)),
                    "ad_spend_eur": round(float(rng.uniform(0, 10)), 2),
                }
            )

    csv_path = tmp_path / "eval_dataset.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture(scope="module")
def eval_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_dataset(tmp_path_factory.mktemp("eval"))


# ---------------------------------------------------------------------------
# Offline agent simulation (no LLM required)
# ---------------------------------------------------------------------------


def _simulated_state(payload: dict, inject_bad: bool) -> dict:
    price = (
        payload["unit_cost_eur"] * 0.5
        if inject_bad
        else payload["model_recommended_price_eur"]
    )
    invented = " Competitor sells at 543.21 EUR." if inject_bad else ""
    return {
        "analyst": AnalystFindings(
            summary=f"Elasticity is {payload['elasticity']} with R² "
            f"{payload['r_squared']}.",
            findings=[
                f"Current price is {payload['current_price_eur']} EUR "
                f"vs cost {payload['unit_cost_eur']} EUR."
            ],
            data_quality_notes=list(payload["model_warnings"]),
        ),
        "strategist": StrategistRecommendation(
            recommended_price_eur=price,
            rationale=f"Model optimum is "
            f"{payload['model_recommended_price_eur']} EUR.{invented}",
            expected_impact="Higher weekly profit.",
            risks=["Demand estimate is uncertain."],
        ),
        "reviewer": ReviewerVerdict(
            verdict="approve",
            checks_performed=["cost floor", "price band"],
            concerns=[],
        ),
    }


def _payload_numbers(payload: dict) -> list[float]:
    return [float(v) for v in payload.values() if isinstance(v, (int, float))]


# ---------------------------------------------------------------------------
# Parametrised tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("product_id,market", EXAMPLE_CASES)
def test_agent_output_structure(
    product_id: str, market: str, eval_dataset: Path
) -> None:
    """Agent output must parse into the AgentAnalysisResponse schema."""
    from app.data_source import CsvDataSource

    source = CsvDataSource(str(eval_dataset))
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta_row = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta_row["product_name"], meta_row["category"]
    )

    state = _simulated_state(payload, inject_bad=False)
    # Should not raise
    AgentAnalysisResponse(
        product_id=product_id,
        market=market,
        analyst=state["analyst"],
        strategist=state["strategist"],
        reviewer=state["reviewer"],
        guardrail=GuardrailReport(passed=True, violations=[]),
        model="eval",
        cached=False,
    )


@pytest.mark.parametrize("product_id,market", EXAMPLE_CASES)
def test_agent_output_grounding(
    product_id: str, market: str, eval_dataset: Path
) -> None:
    """Cited numbers in analyst/strategist text must exist in the payload
    (±5%)."""
    from app.data_source import CsvDataSource

    source = CsvDataSource(str(eval_dataset))
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta_row = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta_row["product_name"], meta_row["category"]
    )

    state = _simulated_state(payload, inject_bad=False)
    analyst, strategist = state["analyst"], state["strategist"]
    allowed = _payload_numbers(payload)
    cited_text = " ".join(
        [
            analyst.summary,
            *analyst.findings,
            strategist.rationale,
            strategist.expected_impact,
        ]
    )
    bad = ungrounded_numbers(cited_text, allowed)
    assert not bad, f"Ungrounded numbers in output: {bad}"


@pytest.mark.parametrize("product_id,market", EXAMPLE_CASES)
def test_agent_output_safety(product_id: str, market: str, eval_dataset: Path) -> None:
    """Recommended price must clear cost floor and plausibility guardrails."""
    from app.data_source import CsvDataSource

    source = CsvDataSource(str(eval_dataset))
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta_row = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta_row["product_name"], meta_row["category"]
    )

    state = _simulated_state(payload, inject_bad=False)
    violations = validate_recommendation(
        state["strategist"],
        unit_cost=result.unit_cost,
        current_price=result.current_price,
        min_observed=result.min_observed_price,
        max_observed=result.max_observed_price,
    )
    assert not violations, f"Safety guardrail violations: {violations}"


@pytest.mark.parametrize("product_id,market", EXAMPLE_CASES)
def test_agent_output_consistency(
    product_id: str, market: str, eval_dataset: Path
) -> None:
    """Reviewer must not approve when safety guardrails detect violations."""
    from app.data_source import CsvDataSource

    source = CsvDataSource(str(eval_dataset))
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta_row = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta_row["product_name"], meta_row["category"]
    )

    state = _simulated_state(payload, inject_bad=False)
    violations = validate_recommendation(
        state["strategist"],
        unit_cost=result.unit_cost,
        current_price=result.current_price,
        min_observed=result.min_observed_price,
        max_observed=result.max_observed_price,
    )
    reviewer = state["reviewer"]
    assert not (
        violations and reviewer.verdict == "approve"
    ), f"Reviewer approved despite violations: {violations}"


# ---------------------------------------------------------------------------
# Negative tests: inject_bad must trigger failures in grounding + safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("product_id,market", [EXAMPLE_CASES[0]])
def test_inject_bad_triggers_grounding_failure(
    product_id: str, market: str, eval_dataset: Path
) -> None:
    """--inject-bad simulation produces an ungrounded number the check
    catches."""
    from app.data_source import CsvDataSource

    source = CsvDataSource(str(eval_dataset))
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta_row = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta_row["product_name"], meta_row["category"]
    )

    state = _simulated_state(payload, inject_bad=True)
    analyst, strategist = state["analyst"], state["strategist"]
    allowed = _payload_numbers(payload)
    cited_text = " ".join(
        [
            analyst.summary,
            *analyst.findings,
            strategist.rationale,
            strategist.expected_impact,
        ]
    )
    bad = ungrounded_numbers(cited_text, allowed)
    assert bad, "Expected grounding failure not detected for injected bad output"


@pytest.mark.parametrize("product_id,market", [EXAMPLE_CASES[0]])
def test_inject_bad_triggers_safety_failure(
    product_id: str, market: str, eval_dataset: Path
) -> None:
    """--inject-bad simulation produces a below-cost price the safety check
    catches."""
    from app.data_source import CsvDataSource

    source = CsvDataSource(str(eval_dataset))
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta_row = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta_row["product_name"], meta_row["category"]
    )

    state = _simulated_state(payload, inject_bad=True)
    violations = validate_recommendation(
        state["strategist"],
        unit_cost=result.unit_cost,
        current_price=result.current_price,
        min_observed=result.min_observed_price,
        max_observed=result.max_observed_price,
    )
    assert violations, "Expected safety violation not detected for injected bad output"
