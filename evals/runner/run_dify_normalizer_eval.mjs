import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const sourcePath = path.join(root, "dify/workflow/memory-normalizer.js");
const reportPath = path.join(root, "evals/reports/dify-normalizer-eval-latest.json");
const source = fs.readFileSync(sourcePath, "utf8");
const normalize = vm.runInNewContext(`${source}\nmain`);

const cases = [
  {
    name: "explicit_case_wins",
    input: { query: "改查 A20260002", confirmed_case_id: "A20260001", recent_case_ids: '["A20260001"]', dialog_count: 3, last_case_confirmed_turn: 1 },
    expect: { case_id: "A20260002", next_turn: 4, recent_case_ids_next: '["A20260001","A20260002"]' }
  },
  {
    name: "single_recent_reference_resolves",
    input: { query: "刚才那个病例进度呢", confirmed_case_id: "A20260001", recent_case_ids: '["A20260001"]', dialog_count: 5, last_case_confirmed_turn: 1 },
    expect: { case_id: "A20260001", case_reference_status_next: "resolved", is_task_continuation: true }
  },
  {
    name: "multiple_recent_cases_are_ambiguous",
    input: { query: "刚才那个病例进度呢", confirmed_case_id: "A20260002", recent_case_ids: '["A20260001","A20260002"]', dialog_count: 5, last_case_confirmed_turn: 2 },
    expect: { case_id: "", case_reference_status_next: "ambiguous", needs_case_id: true }
  },
  {
    name: "memory_expires_after_ten_turns",
    input: { query: "刚才那个病例进度呢", confirmed_case_id: "A20260001", recent_case_ids: '["A20260001"]', dialog_count: 12, last_case_confirmed_turn: 1 },
    expect: { case_id: "", needs_case_id: true, recent_case_ids_next: "[]" }
  },
  {
    name: "other_case_clears_candidates",
    input: { query: "我想查另一个病例", confirmed_case_id: "A20260001", recent_case_ids: '["A20260001"]', dialog_count: 2, last_case_confirmed_turn: 1 },
    expect: { case_id: "", needs_case_id: true, recent_case_ids_next: "[]" }
  },
  {
    name: "pending_slot_accepts_case_id",
    input: { query: "A20260001", active_intent: "case_status", pending_action: "collect_case_id", dialog_count: 2 },
    expect: { case_id: "A20260001", next_action: "", next_turn: 3 }
  },
  {
    name: "high_risk_interrupts_pending_task",
    input: { query: "患者呼吸困难并且剧痛", active_intent: "case_status", pending_action: "collect_case_id", dialog_count: 2 },
    expect: { risk_hit: true, next_action: "handoff" }
  },
  {
    name: "http_fault_token_maps_to_header_value",
    input: { query: "查询病例 A20260001 ERR500", dialog_count: 1 },
    expect: { case_id: "A20260001", fault_mode: "http_500" }
  },
  {
    name: "timeout_token_maps_to_header_value",
    input: { query: "查询病例 A20260001 TIMEOUT", dialog_count: 1 },
    expect: { case_id: "A20260001", ticket_id: "", fault_mode: "timeout" }
  }
];

const results = cases.map((testCase) => {
  const actual = normalize(testCase.input);
  let failure = "";
  try {
    for (const [key, value] of Object.entries(testCase.expect)) {
      assert.deepEqual(actual[key], value, `${key} mismatch`);
    }
  } catch (error) {
    failure = error.message;
  }
  return { name: testCase.name, result: failure ? "failed" : "passed", failure, actual };
});

const passed = results.filter((item) => item.result === "passed").length;
const report = {
  evidence_type: "executable_dify_code_eval",
  source: "dify/workflow/memory-normalizer.js",
  total: results.length,
  passed,
  failed: results.length - passed,
  results
};

fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
console.log(`Dify normalizer eval: ${passed}/${results.length} passed`);
if (passed !== results.length) process.exitCode = 1;
