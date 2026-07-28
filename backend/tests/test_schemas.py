"""Schema validation: valid inputs pass, malformed inputs are rejected."""

import pytest
from app.schemas import AgentAnalysisRequest, StrategistRecommendation
from pydantic import ValidationError


def test_agent_request_valid() -> None:
    req = AgentAnalysisRequest(product_id="SKU-1042", market="FR")
    assert req.product_id == "SKU-1042"


@pytest.mark.parametrize(
    "product_id, market",
    [
        ("DROP TABLE sales", "DE"),  # not a SKU pattern
        ("SKU-1000", "US"),  # unknown market
        ("", "DE"),  # empty id
        ("SKU-" + "9" * 30, "DE"),  # too long
    ],
)
def test_agent_request_rejects_bad_input(product_id: str, market: str) -> None:
    with pytest.raises(ValidationError):
        AgentAnalysisRequest(product_id=product_id, market=market)


def test_strategist_price_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        StrategistRecommendation(
            recommended_price_eur=-5.0,
            rationale="x",
            expected_impact="x",
            risks=[],
        )
