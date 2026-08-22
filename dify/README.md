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

## Browser Regression Results

| Test | Before | Current draft |
|---|---|---|
| Product question | Product answer plus unrelated case-ID prompt | Only product answer |
| Explicit case query | Fell into service-flow RAG | Enters `查询病例状态` HTTP node |
| Case API result | Not reached | Reached; old Render Mock returned 404 for the new test fixture |

## Remaining Before Publish

- Deploy the new FastAPI Backend to a public HTTPS endpoint.
- Replace user-editable doctor identity with a trusted JWT input.
- Update case and ticket URLs, headers, request body, and idempotency key.
- Add explicit error branches for 400/401/403/404/409/429/500 and timeout.
- Update identifier extraction for `CASE-2026-0001` and `TKT-2026-0001`.
- Run the fixed regression suite and obtain user confirmation before publishing.
