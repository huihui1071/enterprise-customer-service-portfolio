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

## Backend Eval

Run:

```bash
backend/.venv/bin/python evals/runner/run_backend_eval.py
```

The report is written to `evals/reports/backend-eval-latest.json` and is labeled `measured`.

## Metric Truthfulness

- Backend permission, idempotency, and assignment metrics may be reported only from the generated report.
- AI route, RAG, citation, high-risk recall, and latency targets remain `target` until the Dify batch runner is connected and executed.
- A browser smoke test proves a specific path, not a population-level accuracy metric.
