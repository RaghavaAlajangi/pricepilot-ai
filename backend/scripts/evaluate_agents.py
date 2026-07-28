"""Lightweight evaluation of the AI agents' output.

For a handful of example product/market cases this script:
  1. builds the same ML payload the agents receive in production,
  2. obtains agent output (live LLM run, or an offline simulation when
     no OPENAI_API_KEY is set so the checks themselves stay testable),
  3. runs four checks over the output:
       structure   - output parses into the expected Pydantic schemas
       grounding   - numbers the agents cite exist in the payload (±5%)
       safety      - price above cost, within ±30% of current, in range
       consistency - if guardrails flag violations, the reviewer must
                     not have said "approve"

Usage:
    python -m scripts.evaluate_agents                # live (needs API key) or offline
    python -m scripts.evaluate_agents --inject-bad   # prove the checks catch bad output

Exit code 0 = all checks passed, 1 = at least one failure.
"""

import argparse
import sys

from app.agents.graph import run_workflow
from app.config import get_settings
from app.data_source import CsvDataSource
from app.guardrails import ungrounded_numbers, validate_recommendation
from app.schemas import (
    AgentAnalysisResponse,
    AnalystFindings,
    GuardrailReport,
    ReviewerVerdict,
    StrategistRecommendation,
)
from app.services import pricing

EXAMPLE_CASES = [("SKU-1000", "DE"), ("SKU-1010", "FR"), ("SKU-1020", "CH")]


def simulated_state(payload: dict, inject_bad: bool) -> dict:
    """Offline stand-in for the LLM: builds output from the payload itself.

    With --inject-bad the strategist invents a number and prices below
    cost, which the checks below must catch.
    """
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


def payload_numbers(payload: dict) -> list[float]:
    """All numeric values in the payload = the set of 'grounded' numbers."""
    return [float(v) for v in payload.values() if isinstance(v, (int, float))]


def evaluate_case(
    product_id: str,
    market: str,
    source: CsvDataSource,
    live: bool,
    inject_bad: bool,
) -> list[tuple[str, bool, str]]:
    """Run all checks for one case. Returns (check_name, passed, detail)."""
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta["product_name"], meta["category"]
    )

    state = (
        run_workflow(payload) if live else simulated_state(payload, inject_bad)
    )
    analyst, strategist, reviewer = (
        state["analyst"],
        state["strategist"],
        state["reviewer"],
    )

    checks: list[tuple[str, bool, str]] = []

    # 1. structure: everything assembles into the response schema
    try:
        AgentAnalysisResponse(
            product_id=product_id,
            market=market,
            analyst=analyst,
            strategist=strategist,
            reviewer=reviewer,
            guardrail=GuardrailReport(passed=True, violations=[]),
            model="eval",
            cached=False,
        )
        checks.append(("structure", True, "output matches expected schemas"))
    except Exception as exc:
        checks.append(("structure", False, str(exc)))

    # 2. grounding: cited numbers must exist in the payload
    allowed = payload_numbers(payload)
    cited_text = " ".join(
        [
            analyst.summary,
            *analyst.findings,
            strategist.rationale,
            strategist.expected_impact,
        ]
    )
    bad_numbers = ungrounded_numbers(cited_text, allowed)
    checks.append(
        (
            "grounding",
            not bad_numbers,
            f"ungrounded numbers: {bad_numbers}"
            if bad_numbers
            else "all cited numbers found in payload",
        )
    )

    # 3. safety: recommendation clears cost / plausibility guardrails
    violations = validate_recommendation(
        strategist,
        unit_cost=result.unit_cost,
        current_price=result.current_price,
        min_observed=result.min_observed_price,
        max_observed=result.max_observed_price,
    )
    checks.append(
        (
            "safety",
            not violations,
            "; ".join(violations) or "recommendation is safe",
        )
    )

    # 4. consistency: reviewer must not approve an unsafe recommendation
    consistent = not (violations and reviewer.verdict == "approve")
    checks.append(
        (
            "consistency",
            consistent,
            "reviewer approved despite guardrail violations"
            if not consistent
            else f"reviewer verdict '{reviewer.verdict}' consistent with "
            f"guardrails",
        )
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inject-bad",
        action="store_true",
        help="simulate a bad agent output to demonstrate the checks fire",
    )
    args = parser.parse_args()

    settings = get_settings()
    live = bool(settings.openai_api_key) and not args.inject_bad
    mode = "LIVE (real LLM)" if live else "OFFLINE (simulated agent output)"
    print(f"Agent output evaluation - mode: {mode}\n")

    source = CsvDataSource(settings.dataset_path)
    failures = 0
    for product_id, market in EXAMPLE_CASES:
        print(f"== {product_id} / {market} ==")
        for name, passed, detail in evaluate_case(
            product_id, market, source, live, args.inject_bad
        ):
            status = "PASS" if passed else "FAIL"
            failures += not passed
            print(f"  [{status}] {name:12s} {detail}")
        print()

    print(
        f"{'All checks passed.' if failures == 0 else f'{failures} check(s) FAILED.'}"
    )
    if args.inject_bad and failures:
        print("(Expected: --inject-bad deliberately produces unsafe output.)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
