# Deployment Runbook

## Render Blueprint

The repository-root `render.yaml` defines a free Docker web service. Render generates `JWT_SECRET` automatically. The demo database uses ephemeral storage and is rebuilt from the fixed seed after a restart; this is reproducible for a portfolio demo but is not a production persistence design.

## 1. Local Python

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify:

```bash
curl http://127.0.0.1:8000/health
```

## 2. Docker Compose

```bash
cd deploy
cp env.example .env
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8000/health
```

The current development machine does not have Docker installed, so the Dockerfile and Compose configuration are prepared but not yet build-verified.

## 3. Public HTTPS Deployment Requirements

- Replace `JWT_SECRET` with a managed secret.
- Disable fault injection.
- Use a persistent disk or PostgreSQL.
- Terminate TLS at the platform or reverse proxy.
- Restrict CORS to the intended Dify origin if browser clients are added.
- Configure health checks and restart policy.
- Capture stdout JSON logs centrally.
- Do not deploy real patient or company data.

## 4. Dify Cutover

```text
deploy Backend
→ verify /health
→ obtain test JWT
→ update Dify HTTP nodes in draft
→ run case, ticket, high-risk, permission, and fault tests
→ compare Eval release gates
→ request publication confirmation
→ publish or roll back
```

## 5. Incident Checks

| Symptom | Check | Action |
|---|---|---|
| Dify timeout | Backend health and request logs | Do not blindly recreate tickets; retry with same idempotency key |
| 401 | Token expiry and issuer | Refresh mock token; never fall back to request `doctor_id` |
| 403/404 case | Audit internal reason | Keep public response ambiguous; fix Membership or Assignment only through admin flow |
| 409 | Idempotency key and payload hash | Reuse the original payload or issue a new key for a genuinely new request |
| 429 | `Retry-After` | Back off and show a temporary user message |
| 500/503 | `trace_id` and dependency state | Degrade to manual support for urgent requests |
