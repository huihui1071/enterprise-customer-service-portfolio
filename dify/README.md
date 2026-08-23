# Dify Workflow

## Versioned DSL

- `workflow/v0-current-export.yml`: initial exported workflow, 45 nodes and 45 edges.
- `workflow/v1-routing-fixed-draft.yml`: removed the duplicate case-ID clarification path, 43 nodes and 43 edges.
- `workflow/v2-routing-and-boolean-fixed-draft.yml`: additionally fixes `status_query_hint` from string comparison to boolean comparison.

## Cloud Draft Changes

The current Dify cloud draft has been modified but not published:

1. Removed the erroneous `病例状态分流 ELSE -> 会话状态-等待病例号` edge.
2. Removed the redundant legacy state and reply nodes.
3. Preserved exactly three routes: case query, missing-case clarification, and normal intent classification.
4. Re-selected `status_query_hint` as a boolean variable so explicit case queries enter the HTTP node.
5. Connected the case and ticket HTTP nodes to the public Render Demo Adapter.
6. Rebuilt dynamic URLs and the case-result prompt with Dify variable chips instead of literal `{{...}}` text.

The draft was autosaved on 2026-08-22 and has not been published. The cloud draft is newer than the checked-in v2 DSL snapshot.

## Browser Regression Results

| Test | Before | Current draft |
|---|---|---|
| Product question | Product answer plus unrelated case-ID prompt | Only product answer |
| Explicit case query | Fell into service-flow RAG | Enters `查询病例状态` HTTP node |
| Case API result | Not reached | Returned case status, update time and next step |
| High-risk clinical issue | Not connected | Created a P0 ticket and assigned `high-risk-support` |
| Ticket query | Not connected | Returned ticket status, priority and assignee |

Focused Dify + Render smoke result: **4/4 passed**. This is not a substitute for the full 150-case evaluation.

## Conversation Memory Draft

The cloud draft now stores an authorized case ID in `confirmed_case_id` and `active_case_id`, ends the slot-filling state after a successful query, lets explicit IDs override memory, resolves a single-case reference such as “我刚刚说的那个病例”, treats “另一个病例” as a request for a new ID, and keeps high-risk rules ahead of pending clarification.

Focused browser memory smoke result on 2026-08-23: **9/9 passed**. The cloud draft clears both `active_case_id` and `confirmed_case_id` when the user switches to another case, prevents stale-case reuse, safely clarifies references after multiple authorized cases, and expires a case reference after more than ten completed user turns.

`workflow/memory-normalizer.js` is the versioned source synchronized to the cloud Code node. It adds deterministic outputs for `next_turn`, `recent_case_ids_next`, and `case_reference_status_next`. Run `node evals/runner/run_dify_normalizer_eval.mjs` to verify the same code. The cloud success-assignment node writes the recent-case list, confirmation turn, and reference status after an authorized query. The public `记忆-轮次递增` node now updates `turn_index` before every business branch; multi-case ambiguity and ten-turn expiry both have cloud end-to-end evidence.

The case-query HTTP node now has a five-second timeout, controlled fault-injection header, retry policy, and explicit exception branch. Failures return a deterministic fallback instead of an LLM-generated status, then clear active, confirmed, and recent case memory. Focused case-error browser smoke result: **5/5 passed**.

The high-risk ticket-creation and ticket-query HTTP nodes now use the same controlled fault header, five-second connect/read/write timeouts, three retries, and explicit exception branches. Ticket creation failures state that handoff has not completed and retain emergency guidance; ticket-query failures never infer a ticket state. Focused ticket-error browser smoke result: **6/6 passed**.

Authorization-change memory safety is now executable through the demo-only `AUTH_REVOKED` boundary token. A previously authorized case is rechecked by the Backend, the simulated revocation returns the same public `CASE_UNAVAILABLE` denial used by object authorization, and the Dify failure branch clears active, confirmed, and recent case memory. Focused browser sequence result: **3/3 turns passed**.

## Remaining Before Publish

- Run the full 150-case evaluation and analyze failure slices.
- Replace the Demo Adapter's fixed identity with production-grade trusted identity propagation before any real-data use.
- Obtain user confirmation before publishing the Dify draft.
