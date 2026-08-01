"""Live agent evaluation: run the real LLM workflow over example cases and
sanity-check what the agents actually said.

The offline variant of these checks (simulated agent output, no API key)
lives in tests/test_agent_eval.py and runs on every PR. This script applies
the SAME four checks to REAL LLM output, so it needs OPENAI_API_KEY and
costs a few thousand tokens per run (3 cases x 3 small calls). CI runs it
when a push to main touches LLM-facing code (or on manual dispatch) and as
a gate before deployment.

Checks per case:
  structure   — output parses into the AgentAnalysisResponse schema
  grounding   — numbers cited by analyst/strategist exist in the payload (±5%)
  safety      — recommendation clears cost floor / price band / observed range
  consistency — reviewer must not approve a recommendation failing guardrails

Usage (from backend/):
  DATASET_PATH=../data/dataset.csv python -m scripts.evaluate_agents
"""

import sys

from pydantic import ValidationError

from app.agents.graph import run_workflow
from app.agents.llm_client import AgentError
from app.config import get_settings
from app.data_source import CsvDataSource
from app.guardrails import (
    MAX_MOVE_FROM_CURRENT,
    ungrounded_numbers,
    validate_recommendation,
)
from app.logging_conf import configure_logging
from app.schemas import AgentAnalysisResponse, GuardrailReport
from app.services import pricing

EXAMPLE_CASES: list[tuple[str, str]] = [
    ("SKU-1000", "DE"),
    ("SKU-1010", "FR"),
    ("SKU-1020", "CH"),
]

CheckResult = tuple[str, bool, str]  # (check name, passed, detail)


def _payload_numbers(payload: dict) -> list[float]:
    return [float(v) for v in payload.values() if isinstance(v, (int, float))]


def _context_snippets(text: str, values: list[float]) -> str:
    """Show each ungrounded number with surrounding text for diagnosis."""
    snippets = []
    for value in values:
        for form in (f"{value:g}", f"{value:.2f}", f"{value:.1f}"):
            pos = text.find(form)
            if pos != -1:
                start, end = max(0, pos - 35), pos + len(form) + 35
                snippets.append(f"{value} in '...{text[start:end]}...'")
                break
        else:
            snippets.append(str(value))
    return "; ".join(snippets)


def evaluate_case(
    source: CsvDataSource, product_id: str, market: str
) -> list[CheckResult]:
    """Run the real agent workflow for one case and return the four checks."""
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta_row = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta_row["product_name"], meta_row["category"]
    )

    state = run_workflow(payload)
    analyst, strategist, reviewer = (
        state["analyst"],
        state["strategist"],
        state["reviewer"],
    )
    total_tokens = sum(s.input_tokens + s.output_tokens for s in state["steps"])
    print(f"  ran {len(state['steps'])} agent steps, {total_tokens} tokens")

    checks: list[CheckResult] = []

    # safety -------------------------------------------------------------
    violations = validate_recommendation(
        strategist,
        unit_cost=result.unit_cost,
        current_price=result.current_price,
        min_observed=result.min_observed_price,
        max_observed=result.max_observed_price,
    )
    checks.append(("safety", not violations, "; ".join(violations)))

    # structure ----------------------------------------------------------
    try:
        AgentAnalysisResponse(
            product_id=product_id,
            market=market,  # type: ignore[arg-type]  # validated by the schema
            analyst=analyst,
            strategist=strategist,
            reviewer=reviewer,
            guardrail=GuardrailReport(passed=not violations, violations=violations),
            model=get_settings().openai_model,
            cached=False,
            steps=state["steps"],
        )
        checks.append(("structure", True, ""))
    except ValidationError as exc:
        checks.append(("structure", False, str(exc)))

    # grounding ----------------------------------------------------------
    # The strategist's own recommended price is its decision, not a cited
    # fact, so it is allowed even when it differs from the model optimum
    # (safety still bounds it above). Policy bounds stated in the prompts
    # (e.g. "within 30% of current price") are grounded context, not
    # invented data.
    allowed = _payload_numbers(payload) + [
        strategist.recommended_price_eur,
        MAX_MOVE_FROM_CURRENT * 100,
    ]
    cited_text = " ".join(
        [
            analyst.summary,
            *analyst.findings,
            strategist.rationale,
            strategist.expected_impact,
        ]
    )
    bad = ungrounded_numbers(cited_text, allowed)
    detail = f"ungrounded: {_context_snippets(cited_text, bad)}" if bad else ""
    checks.append(("grounding", not bad, detail))

    # consistency ----------------------------------------------------------
    inconsistent = bool(violations) and reviewer.verdict == "approve"
    checks.append(
        (
            "consistency",
            not inconsistent,
            "reviewer approved despite guardrail violations" if inconsistent else "",
        )
    )
    return checks


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    if not settings.openai_api_key:
        print(
            "ERROR: OPENAI_API_KEY is not set. This script evaluates REAL "
            "LLM output; for the offline checks run: pytest tests -m agent"
        )
        sys.exit(2)

    source = CsvDataSource(settings.dataset_path)
    failures = 0
    for product_id, market in EXAMPLE_CASES:
        print(f"\n=== {product_id} / {market} (model: {settings.openai_model}) ===")
        try:
            checks = evaluate_case(source, product_id, market)
        except AgentError as exc:
            print(f"  FAIL  workflow      {exc}")
            failures += 1
            continue
        for name, passed, detail in checks:
            status = "PASS" if passed else "FAIL"
            print(f"  {status}  {name:<12} {detail}".rstrip())
            failures += 0 if passed else 1

    print(
        f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} failed check(s) "
        f"across {len(EXAMPLE_CASES)} live cases."
    )
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
