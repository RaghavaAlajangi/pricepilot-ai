"""Guardrails: code-level checks on agent output before it reaches the client.

Two kinds of checks live here (reused by the offline regression tests in
tests/test_agent_eval.py and the live evaluation in
scripts/evaluate_agents.py):
- safety:    the recommended price must clear cost and stay in a plausible band
- grounding: numbers an agent cites must actually appear in its input payload
"""

import re

from .schemas import StrategistRecommendation

COST_FLOOR_MARGIN = 1.02  # never recommend below cost + 2%
MAX_MOVE_FROM_CURRENT = 0.30  # max +/-30% vs current price
# Lookbehind stops digits inside identifiers ("SKU-1000") being read as
# negative numbers; a genuine minus is preceded by space/punctuation.
NUMBER_PATTERN = re.compile(r"(?<![\w-])-?\d+(?:[.,]\d+)?")
GROUNDING_TOLERANCE = 0.05  # cited numbers may differ 5% from a source number


def validate_recommendation(
    rec: StrategistRecommendation,
    unit_cost: float,
    current_price: float,
    min_observed: float,
    max_observed: float,
) -> list[str]:
    """Return a list of violations (empty list = safe recommendation)."""
    price = rec.recommended_price_eur
    violations: list[str] = []
    if price < unit_cost * COST_FLOOR_MARGIN:
        violations.append(
            f"Recommended price {price:.2f} EUR is below the cost floor "
            f"({unit_cost:.2f} EUR cost + 2% margin)."
        )
    move = abs(price - current_price) / current_price
    if move > MAX_MOVE_FROM_CURRENT:
        violations.append(
            f"Recommended price {price:.2f} EUR moves {move:.0%} from the "
            f"current price {current_price:.2f} EUR (limit "
            f"{MAX_MOVE_FROM_CURRENT:.0%})."
        )
    if not (min_observed * 0.9 <= price <= max_observed * 1.1):
        violations.append(
            f"Recommended price {price:.2f} EUR is outside the observed price "
            f"range [{min_observed:.2f}, {max_observed:.2f}] EUR (+/-10%)."
        )
    return violations


def extract_numbers(text: str) -> list[float]:
    """Pull all numeric literals out of free text (comma or dot decimals)."""
    return [float(m.replace(",", ".")) for m in NUMBER_PATTERN.findall(text)]


def ungrounded_numbers(text: str, source_numbers: list[float]) -> list[float]:
    """Numbers cited in ``text`` that match no source number within 5%.

    Small integers (< 10) are ignored: they are usually counts, ranks or
    'top 3'-style phrasing rather than data citations.
    """
    ungrounded = []
    for value in extract_numbers(text):
        if abs(value) < 10:
            continue
        if not any(
            abs(value - src) <= GROUNDING_TOLERANCE * max(abs(src), 1.0)
            for src in source_numbers
        ):
            ungrounded.append(value)
    return ungrounded
