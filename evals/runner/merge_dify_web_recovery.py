"""Merge focused WebApp recovery runs into the original 150-case API report."""

import importlib.util
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "eval" / "eval_cases.json"
API_REPORT = ROOT / "evals" / "reports" / "dify-api-eval-latest.json"
WEB_REPORT = ROOT / "evals" / "reports" / "dify-web-recovery-latest.json"
ROUND2_REPORT = ROOT / "evals" / "reports" / "dify-web-round2-latest.json"
REPORT = ROOT / "evals" / "reports" / "dify-consolidated-eval-latest.json"
BAD_CASES = ROOT / "evals" / "reports" / "dify-consolidated-bad-cases-latest.json"


def load_api_runner():
    path = Path(__file__).with_name("run_dify_api_eval.py")
    spec = importlib.util.spec_from_file_location("dify_api_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def answer_after_input(paragraphs, user_input):
    indexes = [index for index, text in enumerate(paragraphs) if text == user_input]
    start = indexes[-1] + 1 if indexes else 0
    return "\n\n".join(paragraphs[start:]).strip()


def web_result_to_api_shape(row, result, grader):
    turns = []
    for turn in result["turn_results"]:
        failure = "\n".join(turn.get("failures", []))
        turns.append({
            "input": turn["input"],
            "http_status": 200 if not failure else 400,
            "latency_ms": turn["elapsed_ms"],
            "error": "webapp_workflow_error" if failure else None,
            "answer": answer_after_input(turn.get("paragraphs", []), turn["input"]),
            "message_id": None,
            "conversation_id": None,
            "metadata": {"source": "published_dify_webapp"},
            "error_response": {"message": failure} if failure else None,
        })
    return {
        "eval_id": row["eval_id"],
        "category": row["category"],
        "severity": row["severity"],
        "expected_route": row["expected_route"],
        "turn_results": turns,
        "recovery_surface": "published_dify_webapp",
        **grader.grade(row, turns),
    }


def main():
    grader = load_api_runner()
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    rows_by_id = {row["eval_id"]: row for row in rows}
    original = json.loads(API_REPORT.read_text(encoding="utf-8"))
    web = json.loads(WEB_REPORT.read_text(encoding="utf-8"))
    round2 = json.loads(ROUND2_REPORT.read_text(encoding="utf-8"))
    results_by_id = {item["eval_id"]: item for item in original["results"]}

    for web_run in (web, round2):
        for item in web_run["results"]:
            row = rows_by_id[item["eval_id"]]
            results_by_id[item["eval_id"]] = web_result_to_api_shape(row, item, grader)

    results = [results_by_id[row["eval_id"]] for row in rows]
    evaluated = [item for item in results if item.get("evaluable", True)]
    execution_errors = [item for item in results if not item.get("evaluable", True)]
    failures = [item for item in evaluated if not item["passed"]]
    latencies = [turn["latency_ms"] for item in results for turn in item["turn_results"]]
    category_totals = Counter(item["category"] for item in results)
    category_evaluated = Counter(item["category"] for item in evaluated)
    category_passed = Counter(item["category"] for item in evaluated if item["passed"])

    report = {
        "report_type": "dify_consolidated_eval",
        "metric_status": "measured",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": "synthetic-eval-v2",
        "target_surface": "published_dify_chatflow_api_plus_focused_webapp_recovery",
        "recovered_case_count": len(web["results"]),
        "post_publish_regression_case_count": len(round2["results"]),
        "summary": {
            "passed": sum(item["passed"] for item in evaluated),
            "total": len(results),
            "evaluated": len(evaluated),
            "execution_errors": len(execution_errors),
            "pass_rate": sum(item["passed"] for item in evaluated) / len(evaluated),
            "p50_latency_ms": grader.percentile(latencies, 0.50),
            "p95_latency_ms": grader.percentile(latencies, 0.95),
            "release_blocker_failures": sum(
                item["severity"] == "release_blocker" for item in failures
            ),
            "category_results": {
                name: {
                    "passed": category_passed[name],
                    "evaluated": category_evaluated[name],
                    "execution_errors": total - category_evaluated[name],
                    "total": total,
                }
                for name, total in category_totals.items()
            },
        },
        "methodology_notes": [
            "125 unchanged cases retain the original published API response evidence.",
            "25 rerun cases use the published app through its public WebApp after balance recovery.",
            "5 previously failing cases were rerun again after the routing and fallback fixes were published; these latest responses take precedence.",
            "The report does not claim internal tool traces from user-visible responses.",
        ],
        "results": results,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    BAD_CASES.write_text(json.dumps({
        "behavior_failures": failures,
        "execution_errors": execution_errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
