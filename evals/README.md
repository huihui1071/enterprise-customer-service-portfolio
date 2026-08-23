# Evaluation

## Dataset

`data/eval/eval_cases.json` contains 150 synthetic cases:

- 30 knowledge questions
- 20 intent boundaries
- 20 case access cases
- 20 high-risk handoffs
- 15 ticket operations
- 15 expired, missing, or conflicted knowledge cases
- 15 multi-turn clarification cases
- 15 prompt injection and access-control cases

The dataset is generated from explicit business prompts in `data/eval/build_eval_dataset.py`. Run the zero-cost preflight before every cloud evaluation:

```bash
python3 data/eval/build_eval_dataset.py
python3 evals/runner/validate_eval_dataset.py
```

The preflight rejects placeholders, duplicate conversation signatures, broken IDs, missing assertions, incorrect category counts, and release-blocker samples without safety expectations. Its report is written to `evals/reports/eval-dataset-preflight-latest.json`.

## Dify API Eval

The batch runner targets the **published** Dify Chatflow API:

```bash
DIFY_API_KEY='<secret>' python3 evals/runner/run_dify_api_eval.py --limit 5
DIFY_API_KEY='<secret>' python3 evals/runner/run_dify_api_eval.py
```

It writes raw turn results, user-visible behavior grades, latency percentiles, category slices, and release-blocker failures to `dify-api-eval-latest.json`; failed cases are also written to `dify-api-bad-cases-latest.json`. The runner never creates, stores, or prints an API key.

Run `--limit 5` first as a cost and contract smoke test. A full run should begin only after the tested Dify draft is published with explicit approval.

## Backend Eval

Run:

```bash
backend/.venv/bin/python evals/runner/run_backend_eval.py
```

The report is written to `evals/reports/backend-eval-latest.json` and is labeled `measured`.

## Metric Truthfulness

- Backend permission, idempotency, and assignment metrics may be reported only from the generated report.
- AI route, RAG, citation, high-risk recall, and latency targets remain `target` until the Dify batch runner is executed against the approved published version.
- A browser smoke test proves a specific path, not a population-level accuracy metric.
- API response-based behavior labels do not prove internal node or tool traces; those remain a separate observability requirement.

## Memory Eval

`data/eval/multi_turn_memory_cases.json` defines 15 non-duplicate conversations for slot filling, entity reference, task switching, ambiguity, expiry, authorization changes, and high-risk interruption. The generator embeds them into `EVAL-0121` through `EVAL-0135`, so rebuilding data does not restore the old placeholders.

`evals/reports/dify-memory-smoke-2026-08-23.json` contains the initial focused browser result. Ambiguity, expiry, and authorization-change fixtures now have separate executable browser evidence, but the complete 15-case dataset must still be run through one reproducible end-to-end runner before reporting a unified 15/15 Dify result.

Run the deterministic memory-policy contract suite with:

```bash
python3 evals/runner/run_memory_contract_eval.py
```

The resulting `memory-contract-eval-latest.json` verifies all 15 policy and state-transition contracts without an LLM. It is deliberately reported separately from Dify browser smoke tests: a contract pass proves the intended policy is internally consistent, while only a Dify run proves the workflow wiring and integrations.
