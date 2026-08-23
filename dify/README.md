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

Focused browser memory smoke result on 2026-08-23: **7/7 passed**. The cloud draft clears both `active_case_id` and `confirmed_case_id` when the user switches to another case, preventing stale-case reuse.

`workflow/memory-normalizer.js` is the versioned source for the next cloud revision. It adds deterministic outputs for `next_turn`, `recent_case_ids_next`, and `case_reference_status_next`. Run `node evals/runner/run_dify_normalizer_eval.mjs` to verify the same code that will be pasted into the Dify Code node. Multi-case ambiguity and ten-turn expiry are implemented and executable in this source, but are not counted as cloud end-to-end passes until the output variables and assignment branches are wired in Dify.

## Remaining Before Publish

- Add explicit Dify error branches for 400/401/403/404/409/429/500 and timeout.
- Complete multi-case ambiguity, ten-turn expiry, and authorization-change memory branches.
- Run the full 150-case evaluation and analyze failure slices.
- Replace the Demo Adapter's fixed identity with production-grade trusted identity propagation before any real-data use.
- Obtain user confirmation before publishing the Dify draft.
