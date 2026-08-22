# Mock Backend

FastAPI + SQLite implementation for the synthetic enterprise customer-service portfolio.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API documentation: `http://localhost:8000/docs`

## Test

```bash
pytest -q
```

## Security Notes

- JWT `sub` is the trusted user identity; request body identity fields are ignored.
- Case access combines account, organization, Membership, object ownership, and assistant Assignment checks.
- Missing and forbidden cases share a public message while audit logs retain distinct internal reasons.
- Ticket creation requires `Idempotency-Key`.
- Fault injection is available only when `ENABLE_FAULT_INJECTION=true`.
- Default secrets are for local portfolio use only and must be replaced outside local development.
