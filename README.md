# AI Agent

A production-ready AI Agent built with **Python 3.12 + FastAPI + OpenAI Responses API**.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Client (HTTP/REST)                           │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ POST /api/v1/chat
┌────────────────────────────▼─────────────────────────────────────────┐
│                      FastAPI Application                             │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │ Request ID  │  │ Content-Safety   │  │  Pydantic Validation     │ │
│  │ Middleware  │  │ Input Hook       │  │  (ChatRequest)           │ │
│  └─────────────┘  └──────────────────┘  └──────────────────────────┘ │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────────┐
│                        Agent Core (core.py)                           │
│                                                                       │
│  1. Load session from Short-Term Memory (Redis / in-mem fallback)     │
│  2. Loop:                                                             │
│     a. Call OpenAI Responses API (previous_response_id for continuity)│
│     b. If function_call items → dispatch via Tool Router              │
│     c. Inject function_call_output → repeat                           │
│     d. If text message item → done                                    │
│  3. Append to session; optionally trigger summarizer                  │
│  4. Return reply                                                      │
└─────┬─────────────────────────────────────────────────────────────────┘
      │
      ├─── Tool Router ────────────────────────────────────────────────┐
      │    ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │
      │    │  get_time    │  │ http_request │  │knowledge_search  │    │
      │    │  (timezone)  │  │ (allowlist,  │  │  (local docs/)   │    │
      │    │              │  │  rate limit, │  │  keyword TF)     │    │
      │    │              │  │  timeout)    │  │                  │    │
      │    └──────────────┘  └──────────────┘  └──────────────────┘    │
      │    Tool Safety Layer: rate limit · input validation · timeout  │
      └────────────────────────────────────────────────────────────────┘
      │
      ├─── Memory ────────────────────────────────────────────────────┐
      │    ┌────────────────────────┐  ┌─────────────────────────┐    │
      │    │ Short-Term (Redis)      │  │ Long-Term (Postgres)   │    │
      │    │ Per-session msg history │  │ user_preferences table │    │
      │    │ TTL: 1 hour (default)  │  │ conversation_summaries  │    │
      │    └────────────────────────┘  └─────────────────────────┘    │
      │    Background summarizer (triggered after N messages)         │
      └───────────────────────────────────────────────────────────────┘
      │
      └─── Observability ────────────────────────────────────────────────┐
           OpenTelemetry traces + structured logs (request_id/trace_id)  │
           OTLP → Jaeger (local) / Azure Monitor (production)            │
           └─────────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | File(s) | Purpose |
|---|---|---|
| **API** | `app/api/routes.py`, `app/api/models.py` | FastAPI endpoints, Pydantic models |
| **Agent Core** | `app/agent/core.py` | OpenAI Responses API loop, tool orchestration |
| **System Prompt** | `app/agent/prompts.py` | Behaviour policy for the model |
| **Tool Registry** | `app/tools/registry.py` | JSON schemas + dispatch |
| **Tools** | `app/tools/{get_time,http_request,knowledge_search}.py` | Tool implementations |
| **Tool Safety** | `app/safety/content_safety.py` | Rate limit, domain allowlist, timeouts |
| **Short-Term Memory** | `app/memory/short_term.py` | Redis / in-memory session history |
| **Long-Term Memory** | `app/memory/long_term.py` | Postgres preferences + summaries |
| **Summarizer** | `app/memory/summarizer.py` | Background conversation summarizer |
| **Observability** | `app/observability/telemetry.py` | OpenTelemetry setup, structured logging |
| **Config** | `app/config.py` | All settings via env vars (pydantic-settings) |

---

## Local Run

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- An OpenAI API key

### Option A — Docker Compose (recommended)

```bash
# 1. Clone and enter project
cd ai-agent

# 2. Set your OpenAI key
export OPENAI_API_KEY=sk-...

# 3. Start everything (agent + Redis + Postgres + Jaeger)
docker compose up --build

# 4. Test
curl http://localhost:8000/api/v1/health
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-1","message":"What time is it in Tokyo?"}'

# Tracing UI
open http://localhost:16686   # Jaeger
```

### Option B — Pure Python (no Docker)

```bash
cd ai-agent
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Copy and edit env file
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY

python -m app.main
# → http://localhost:8000
```

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | — | **Yes** | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | No | Model name |
| `APP_ENV` | `development` | No | `development` / `staging` / `production` |
| `REDIS_URL` | `redis://localhost:6379/0` | No | Redis connection; omit for in-memory fallback |
| `POSTGRES_DSN` | `postgresql+asyncpg://...` | No | Async Postgres DSN |
| `ALLOWED_HTTP_DOMAINS` | `httpbin.org,...` | No | Comma-separated domain allowlist |
| `TOOL_TIMEOUT_SECONDS` | `10` | No | Per-tool execution timeout |
| `TOOL_RATE_LIMIT_PER_MINUTE` | `30` | No | Max tool calls per minute |
| `DOCS_PATH` | `docs/` | No | Folder searched by `knowledge_search` |
| `OTLP_ENDPOINT` | _(empty)_ | No | OTLP gRPC endpoint for traces |
| `AZURE_KEYVAULT_URL` | _(empty)_ | No | Key Vault URL (injected in ACA) |

---

## Tool List

### `get_time`
Returns the current date and time for any IANA timezone.
```json
{ "timezone": "America/New_York" }
```

### `http_request`
Performs an outbound HTTP request to an allowed domain.
```json
{ "method": "GET", "url": "https://httpbin.org/get" }
```
Security: domain allowlist, method whitelist, 10 s timeout, input safety scan.

### `knowledge_search`
Searches `.md`/`.txt`/`.rst` files in the `docs/` folder.
```json
{ "query": "how to deploy", "top_k": 3 }
```

---

## Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (no real API calls — uses mock)
pytest tests/integration/ -v

# Full suite + coverage
pytest --cov=app --cov-report=term-missing
```

---

## Deployment (Azure Container Apps)

### One-time setup

```bash
# 1. Create resource group
az group create --name rg-ai-agent --location eastus

# 2. Deploy infrastructure (creates ACR, Redis, Postgres, Key Vault, ACA)
az deployment group create \
  --resource-group rg-ai-agent \
  --template-file infra/main.bicep \
  --parameters infra/parameters.json \
  --parameters openAiApiKey="$OPENAI_API_KEY"
```

### Build and push image

```bash
# Get ACR name from deployment output
ACR=$(az deployment group show \
  --resource-group rg-ai-agent \
  --name main \
  --query "properties.outputs.acrLoginServer.value" -o tsv)

az acr login --name $ACR

docker build -t $ACR/ai-agent:latest .
docker push $ACR/ai-agent:latest
```

### Update the running app

```bash
az containerapp update \
  --name aiagent-app \
  --resource-group rg-ai-agent \
  --image $ACR/ai-agent:latest
```

### CI/CD via GitHub Actions

Required secrets in GitHub repository settings:

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | App registration client ID (federated OIDC) |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_RESOURCE_GROUP` | `rg-ai-agent` |
| `ACR_LOGIN_SERVER` | e.g. `aiagentacrXXXX.azurecr.io` |
| `CONTAINER_APP_NAME` | `aiagent-app` |

Push to `main` to trigger lint → tests → build → deploy.

---

## Validation Checklist

Use this checklist to confirm end-to-end operation after deployment:

```
[ ] GET /api/v1/health returns {"status":"ok"}
[ ] GET /api/v1/tools returns all 3 tools (get_time, http_request, knowledge_search)
[ ] POST /api/v1/chat with "What time is it in UTC?" → tools_called contains "get_time"
[ ] POST /api/v1/chat with same session_id again → conversation continues (context maintained)
[ ] POST /api/v1/chat with "rm -rf /" → 400 response (content safety)
[ ] POST /api/v1/chat asking to fetch https://evil.com → tool returns error (domain not allowed)
[ ] DELETE /api/v1/sessions/{id} returns 204
[ ] Logs contain request_id and trace_id fields on every line
[ ] Jaeger UI (or OTLP backend) shows spans for agent.run and tool calls
[ ] On restart with Redis: session history is preserved
[ ] On restart without Redis: falls back to in-memory silently (check logs)
[ ] docker compose up --build completes with all services healthy
[ ] GitHub Actions CI pipeline passes lint + unit + integration tests
[ ] Azure Container Apps shows healthy replicas after deploy
```

---

## Troubleshooting

**`ValidationError` on startup**: Check `.env` — `OPENAI_API_KEY` is required.

**`ContentSafetyError` (400)**: Your message matched a blocked pattern. Rephrase it.

**`ToolSafetyError` (domain not in allowlist)**: Add the domain to `ALLOWED_HTTP_DOMAINS`.

**Agent loop stuck**: A tool call ran into the 10 s timeout or repeated errors. Check `LOG_LEVEL=DEBUG` output.

**Postgres tables not created**: Check the `POSTGRES_DSN` — the app runs DDL on startup. Ensure asyncpg can reach the server.

**Redis not connecting**: The app falls back to in-memory automatically. Check logs for `"Redis unavailable"`.

**Traces not appearing in Jaeger**: Ensure `OTLP_ENDPOINT=http://jaeger:4317` (from inside Docker) and Jaeger is running.
