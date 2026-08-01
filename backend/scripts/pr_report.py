"""Generate a markdown PR comment from pytest JSON reports."""

import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)


def summary_table(report: dict, label: str) -> str:
    if not report:
        return f"### {label}\n_Report not found._\n"

    s = report.get("summary", {})
    total = s.get("total", 0)
    passed = s.get("passed", 0)
    failed = s.get("failed", 0)
    skipped = s.get("skipped", 0)
    duration = round(report.get("duration", 0), 1)
    pct = f"{passed/total:.0%}" if total else "n/a"

    icon = "✅" if failed == 0 else "❌"
    lines = [
        f"### {icon} {label}",
        "",
        "| | |",
        "|---|---|",
        f"| Passed | **{passed}** / {total} ({pct}) |",
        f"| Failed | {failed} |",
        f"| Skipped | {skipped} |",
        f"| Duration | {duration}s |",
    ]

    failures = [t for t in report.get("tests", []) if t.get("outcome") == "failed"]
    if failures:
        lines += ["", "**Failed tests:**", ""]
        for t in failures:
            name = t.get("nodeid", "unknown")
            msg = ""
            call = t.get("call", {})
            if call.get("longrepr"):
                # take just the last line of the traceback
                msg = str(call["longrepr"]).strip().splitlines()[-1]
            lines.append(f"- `{name}`  \n  {msg}")

    return "\n".join(lines)


def regression_section(agent_report: dict, baseline_path: str) -> str:
    bp = Path(baseline_path)
    if not bp.exists() or not agent_report:
        return ""

    with open(bp) as f:
        baseline = json.load(f)

    def rate(r: dict) -> float:
        s = r.get("summary", {})
        t = s.get("total", 0)
        return s.get("passed", 0) / t if t else 0.0

    current = rate(agent_report)
    base = rate(baseline)
    drop = base - current
    threshold = 0.02

    if drop > threshold:
        status = "❌ **REGRESSION DETECTED** — pass rate dropped "
        f"{drop:.1%} (threshold {threshold:.0%})"
    else:
        status = f"✅ Pass rate {current:.0%} (baseline {base:.0%}, "
        f"drop {drop:.1%})"

    return f"\n### 🤖 Agent Regression Gate\n\n{status}\n"


def main() -> None:
    test_report_path = sys.argv[1] if len(sys.argv) > 1 else "test_report.json"
    agent_report_path = sys.argv[2] if len(sys.argv) > 2 else "agent_report.json"
    baseline_path = sys.argv[3] if len(sys.argv) > 3 else "tests/agent_baseline.json"

    test_report = load(test_report_path)
    agent_report = load(agent_report_path)

    body = "\n\n".join(
        [
            "## 🧪 CI Test Results",
            summary_table(test_report, "Backend Tests"),
            summary_table(agent_report, "Agent Regression Tests"),
            regression_section(agent_report, baseline_path),
        ]
    )

    print(body)


if __name__ == "__main__":
    main()
