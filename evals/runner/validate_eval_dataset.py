"""Validate the 150-case dataset before any paid or slow Dify run."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "eval" / "eval_cases.json"
REPORT = ROOT / "evals" / "reports" / "eval-dataset-preflight-latest.json"
EXPECTED = {
    "knowledge": 30,
    "intent_boundary": 20,
    "case_access": 20,
    "high_risk": 20,
    "ticket": 15,
    "knowledge_quality": 15,
    "multi_turn": 15,
    "security": 15,
}


def run():
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    ids = [row.get("eval_id") for row in rows]
    first_inputs = [row.get("turns", [{}])[0].get("content", "").strip() for row in rows]
    conversation_signatures = [
        json.dumps(row.get("turns", []), ensure_ascii=False, sort_keys=True) for row in rows
    ]
    categories = Counter(row.get("category") for row in rows)
    failures = []

    checks = {
        "case_count_is_150": len(rows) == 150,
        "ids_are_unique": len(ids) == len(set(ids)),
        "conversations_are_unique": len(conversation_signatures) == len(set(conversation_signatures)),
        "category_distribution_matches": dict(categories) == EXPECTED,
        "no_placeholder_prompts": not any(text.startswith("模拟") and "测试问题" in text for text in first_inputs),
        "all_have_expected_route": all(row.get("expected_route") for row in rows),
        "all_have_assertions": all(row.get("assertions") for row in rows),
        "all_have_trusted_inputs": all(row.get("inputs", {}).get("doctor_id") for row in rows),
        "all_release_blockers_have_forbidden_behaviors": all(
            row.get("forbidden_behaviors") for row in rows if row.get("severity") == "release_blocker"
        ),
    }
    for name, passed in checks.items():
        if not passed:
            failures.append(name)

    for index, row in enumerate(rows, start=1):
        expected_id = f"EVAL-{index:04d}"
        if row.get("eval_id") != expected_id:
            failures.append(f"non_contiguous_id:{row.get('eval_id')}!= {expected_id}")
        if not row.get("turns") or any(turn.get("role") not in ("user", "assistant") for turn in row["turns"]):
            failures.append(f"invalid_turns:{expected_id}")
        if row.get("category") in ("high_risk", "security", "case_access") and row.get("severity") != "release_blocker":
            failures.append(f"missing_release_blocker:{expected_id}")

    report = {
        "report_type": "eval_dataset_preflight",
        "metric_status": "measured",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": "synthetic-eval-v2",
        "summary": {
            "passed": not failures,
            "case_count": len(rows),
            "unique_input_count": len(set(first_inputs)),
            "release_blocker_count": sum(row.get("severity") == "release_blocker" for row in rows),
            "category_distribution": dict(categories),
        },
        "checks": checks,
        "failures": failures,
        "limitations": [
            "This report validates dataset quality and contracts, not Dify model behavior.",
            "All prompts, identities, cases, and expected results are synthetic.",
        ],
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["summary"]["passed"] else 1)
