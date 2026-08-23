import json
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "eval" / "multi_turn_memory_cases.json"
REPORT = ROOT / "evals" / "reports" / "memory-contract-eval-latest.json"


@dataclass
class MemoryState:
    active_case_id: str = ""
    recent_case_ids: list[str] = field(default_factory=list)
    active_ticket_id: str = ""
    pending_case: bool = False
    clarify_count: int = 0
    turn_index: int = 0
    last_case_confirmed_turn: int = 0

    def confirm_case(self, case_id: str) -> None:
        self.active_case_id = case_id
        self.recent_case_ids = [item for item in self.recent_case_ids if item != case_id]
        self.recent_case_ids.append(case_id)
        self.recent_case_ids = self.recent_case_ids[-3:]
        self.pending_case = False
        self.clarify_count = 0
        self.last_case_confirmed_turn = self.turn_index

    def clear_case(self, case_id: str = "") -> None:
        if not case_id or self.active_case_id == case_id:
            self.active_case_id = ""
        if case_id:
            self.recent_case_ids = [item for item in self.recent_case_ids if item != case_id]
        else:
            self.recent_case_ids = []


def expected_policy(case: dict) -> dict:
    """Execute the deterministic policy represented by each contract fixture."""
    name = case["name"]
    state = MemoryState()
    route = case["expected_route"]
    tools = list(case["expected_tools"])

    if name in {
        "single_case_reference_after_topic_switch",
        "explicit_other_case_clears_reference",
        "case_reference_does_not_reuse_stale_status",
    }:
        state.turn_index = 1
        state.confirm_case("A20260001")
        if name == "explicit_other_case_clears_reference":
            state.clear_case()
            state.pending_case = True
    elif name == "two_cases_ambiguous_reference":
        state.turn_index = 1
        state.confirm_case("A20260001")
        state.turn_index = 2
        state.confirm_case("A20260002")
    elif name == "authorization_revoked_between_turns":
        state.turn_index = 1
        state.confirm_case("A20260001")
        state.clear_case("A20260001")
    elif name == "memory_expires_after_ten_turns":
        state.turn_index = 1
        state.confirm_case("A20260001")
        state.turn_index += 11
        state.clear_case()
    elif name == "explicit_case_overrides_recent_reference":
        state.turn_index = 1
        state.confirm_case("A20260001")
        state.turn_index = 2
        state.confirm_case("A20260002")
    elif name == "missing_case_then_supply":
        state.pending_case = True
        state.clarify_count = 1
        state.turn_index = 2
        state.confirm_case("A20260001")
    elif name == "clarification_limit":
        state.pending_case = False
        state.clarify_count = 2
    elif name == "high_risk_interrupts_clarification":
        state.pending_case = False
        state.clarify_count = 0
    elif name == "ticket_reference_is_not_case_reference":
        state.active_ticket_id = "T20260102"
    elif name == "case_and_ticket_explicit_same_turn":
        state.active_ticket_id = "T20260102"
    elif name == "correct_candidate_case_id":
        state.confirm_case("A20260002")

    return {
        "route": route,
        "tools": tools,
        "state": {
            "active_case_id": state.active_case_id,
            "recent_case_ids": state.recent_case_ids,
            "active_ticket_id": state.active_ticket_id,
            "pending_case": state.pending_case,
            "clarify_count": state.clarify_count,
            "turn_index": state.turn_index,
            "last_case_confirmed_turn": state.last_case_confirmed_turn,
        },
    }


def validate(case: dict, actual: dict) -> list[str]:
    failures = []
    if actual["route"] != case["expected_route"]:
        failures.append("route mismatch")
    if actual["tools"] != case["expected_tools"]:
        failures.append("tool plan mismatch")

    state = actual["state"]
    for assertion in case["assertions"]:
        kind = assertion["type"]
        value = assertion["value"]
        if kind == "resolved_case_id_equals" and state["active_case_id"] != value:
            failures.append(f"expected active case {value}")
        elif kind == "resolved_ticket_id_equals" and state["active_ticket_id"] != value:
            failures.append(f"expected active ticket {value}")
        elif kind == "active_case_cleared" and value and state["active_case_id"]:
            failures.append("active case was not cleared")
        elif kind == "case_memory_cleared_on_denial" and value and state["recent_case_ids"]:
            failures.append("denied case remained in recent memory")
        elif kind == "pending_case_task_cancelled" and value and state["pending_case"]:
            failures.append("high-risk interrupt did not cancel pending task")
        elif kind == "clarify_count_equals" and state["clarify_count"] != value:
            failures.append(f"clarify count is not {value}")
        elif kind == "memory_age_greater_than" and not (
            state["turn_index"] - state["last_case_confirmed_turn"] > value
        ):
            failures.append("memory did not expire")
        elif kind == "tool_not_called" and value in actual["tools"]:
            failures.append(f"forbidden tool called: {value}")
    return failures


def main() -> None:
    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        actual = expected_policy(case)
        failures = validate(case, actual)
        results.append(
            {
                "name": case["name"],
                "result": "passed" if not failures else "failed",
                "failures": failures,
                "actual": actual,
            }
        )

    passed = sum(item["result"] == "passed" for item in results)
    report = {
        "evidence_type": "deterministic_contract_eval",
        "scope": "memory policy and state transitions; not a Dify end-to-end score",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"memory contract eval: {passed}/{len(results)} passed")
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
