"""Fail if agent test pass rate drops more than THRESHOLD below baseline."""

import json
import sys
from pathlib import Path

THRESHOLD = 0.02  # 2%


def pass_rate(report: dict) -> float:
    summary = report["summary"]
    total = summary.get("total", 0)
    if total == 0:
        raise ValueError("No tests found in report.")
    passed = summary.get("passed", 0)
    return passed / total


def main() -> None:
    baseline_path = Path(__file__).parent.parent / "tests" / "agent_baseline.json"
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("agent_report.json")

    if not baseline_path.exists():
        print(f"No baseline found at {baseline_path} — skipping regression check.")
        sys.exit(0)

    with open(report_path) as f:
        current = pass_rate(json.load(f))
    with open(baseline_path) as f:
        baseline = pass_rate(json.load(f))

    drop = baseline - current
    print(f"Baseline pass rate : {baseline:.1%}")
    print(f"Current pass rate  : {current:.1%}")
    print(f"Drop               : {drop:.1%} (threshold: {THRESHOLD:.1%})")

    if drop > THRESHOLD:
        print(
            f"FAIL: agent pass rate dropped by {drop:.1%}, exceeds "
            f"{THRESHOLD:.1%} threshold."
        )
        sys.exit(1)

    print("PASS: regression within acceptable range.")


if __name__ == "__main__":
    main()
