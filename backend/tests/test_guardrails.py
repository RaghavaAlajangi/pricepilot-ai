"""Guardrail checks: safe pass-through, unsafe rejection, grounding."""

from app.guardrails import ungrounded_numbers, validate_recommendation
from app.schemas import StrategistRecommendation


def make_rec(price: float) -> StrategistRecommendation:
    return StrategistRecommendation(
        recommended_price_eur=price,
        rationale="r",
        expected_impact="i",
        risks=[],
    )


BOUNDS = {
    "unit_cost": 40.0,
    "current_price": 80.0,
    "min_observed": 70.0,
    "max_observed": 100.0,
}


def test_safe_recommendation_passes() -> None:
    assert validate_recommendation(make_rec(85.0), **BOUNDS) == []


def test_below_cost_is_flagged() -> None:
    violations = validate_recommendation(make_rec(39.0), **BOUNDS)
    assert any("cost floor" in v for v in violations)


def test_implausible_jump_is_flagged() -> None:
    violations = validate_recommendation(make_rec(120.0), **BOUNDS)
    assert any("current" in v for v in violations)


def test_outside_observed_range_is_flagged() -> None:
    violations = validate_recommendation(make_rec(62.0), **BOUNDS)
    assert any("observed price range" in v for v in violations)


def test_grounded_numbers_are_accepted() -> None:
    text = "Elasticity is -1.8 and the price of 89.95 EUR beats 79.95."
    assert ungrounded_numbers(text, [89.95, 79.95, -1.8, 40.0]) == []


def test_invented_number_is_caught() -> None:
    text = "Revenue will grow to 12345 EUR."
    assert ungrounded_numbers(text, [89.95, 79.95]) == [12345.0]


def test_small_integers_ignored() -> None:
    assert ungrounded_numbers("Top 3 of 5 products", [100.0]) == []


def test_identifier_digits_are_not_numbers() -> None:
    """Digits inside IDs like SKU-1000 must not be read as -1000."""
    text = "For SKU-1000 the price of 89.95 EUR is optimal."
    assert ungrounded_numbers(text, [89.95]) == []
