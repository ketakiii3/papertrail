# Docker: dashboard vs API (troubleshooting notes)

This document records the confusion that came up when running the stack locally: **which URL is the app**, **why port 8000 looked “broken”**, and **how the dashboard talks to the API**.

## Where to open what

| What | URL | Notes |
|------|-----|--------|
| **Web UI (Next.js dashboard)** | `http://localhost:3000` | This is the product UI. |
| **REST API (FastAPI)** | `http://localhost:8000` | JSON endpoints and Swagger. |
| **API interactive docs** | `http://localhost:8000/docs` | Swagger UI. |
| **Health check** | `http://localhost:8000/health` | Quick “is the API up?” check. |
| **Neo4j Browser** (if running) | `http://localhost:7474` | Graph DB UI. |

The dashboard does **not** run on port 8000. If you only open `http://localhost:8000`, you are hitting the API service, not the Next.js frontend.

## Why `http://localhost:8000/` showed `{"detail":"Not Found"}`

FastAPI returns **404 JSON** for paths that have **no registered route**. For a long time there was **no handler for `GET /`**, so opening the **root** URL in a browser looked like an error even when the server was healthy.

**Fix in repo:** `GET /` redirects to `/docs` so the root URL is useful in a browser.

**Valid API examples** (these should return 200 when the stack is up):

- `http://localhost:8000/health`
- `http://localhost:8000/api/v1/stats`

## Dashboard → API: `NEXT_PUBLIC_*` and Docker

The dashboard reads `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` in **client-side** code (browser). Those values are **inlined at Next.js build time** (`npm run build`).

Important details:

1. **Hostnames:** Inside Compose, services reach each other as `http://api-server:8000`, but the **browser runs on your machine** and does **not** resolve the hostname `api-server`. For local use from the host browser, use **`http://localhost:8000`** and **`ws://localhost:8000`**.

2. **Build vs runtime:** Setting `NEXT_PUBLIC_*` only in `environment:` at container runtime is **not enough** if the image was built without those variables—the client bundle may still have empty or wrong URLs. The **`dashboard` Dockerfile** sets build-time `ARG`/`ENV` for `NEXT_PUBLIC_*`, and **`docker-compose.yml`** passes matching **`build.args`** so `npm run build` bakes in the correct base URLs.

3. **After changing API URL config**, rebuild the dashboard image, e.g. `docker compose build dashboard` or `docker compose up --build dashboard`.

## `docker compose up` scope

Running only one service (e.g. `docker compose up dashboard`) still brings up **dependencies** defined in Compose (such as `api-server`, and whatever those depend on). Only services in that dependency chain start; the **full** stack (Ollama, Neo4j, workers, etc.) may not run unless you start the whole project, e.g. `docker compose up` without a limited service list.

## Quick checklist when something looks wrong

1. Open **`http://localhost:3000`** for the UI.
2. Open **`http://localhost:8000/health`**—if this fails, the API container is not listening or not running.
3. If the UI loads but data is empty or requests fail, confirm **`NEXT_PUBLIC_API_URL`** was set at **image build** and points to **`http://localhost:8000`**, then rebuild the dashboard image.

## Ollama: `500` on `/api/generate`, runner crash, or out-of-memory

**What Ollama is used for:** The **contradiction-detector** calls Ollama only for **optional agent reasoning** (a short analysis string). **Finding and storing contradictions** uses NLI + the database; those steps do not require Ollama.

**What goes wrong on small machines:** A **7B** model such as **`mistral`** often needs **several GiB of RAM** for weights plus KV cache on **CPU**. In Docker, logs may show **`total memory` ~4.5 GiB** for the model, **`system memory` ~5–6 GiB** total on the host, **`llama runner process has terminated`**, **`Load failed`**, or **`POST /api/generate` → 500**. That usually means the runner **exited** (often **OOM** or not enough headroom for the rest of the stack).

**What we changed in the repo:** `.env` defaults to a **smaller** model (**`tinyllama`**) so CPU-only / low-RAM setups are more likely to succeed. **`shared/config.py`** also defaults to **`tinyllama`** when `OLLAMA_MODEL` is unset.

**After changing `OLLAMA_MODEL`:**

1. Pull the model into the Ollama container:  
   `docker compose exec ollama ollama pull tinyllama`  
   (Use the same name as in `OLLAMA_MODEL`.)
2. Restart services that load `.env`, e.g.  
   `docker compose up -d --force-recreate contradiction-detector`  
   or restart the whole stack.

**Where to read Ollama logs:** Same terminal as `docker compose up` (mixed with other services), or only Ollama: **`docker compose logs -f ollama`**. In Docker Desktop: open the **`ollama`** container → **Logs**.

## Hugging Face / FinBERT on first claim extraction

The **claim-extractor** image **pre-downloads** FinBERT and the **sentence-transformers** embedding model at **image build** time (see `services/claim-extractor/Dockerfile`), so the first filing after deploy should not wait on Hugging Face. If you use an old image built before that step, the **first** run may still download models into the container cache. Anonymous Hub access may warn about **`HF_TOKEN`**; a token is optional but can help with rate limits.

## Live Feed: “Demo” vs real WebSocket

The dashboard **Live Feed** uses **`NEXT_PUBLIC_WS_URL`** (e.g. `ws://localhost:8000`). When set, the UI connects to **`/ws/feed`** on the API and shows **Live**; events appear when the **contradiction-detector** publishes to Redis. When `NEXT_PUBLIC_WS_URL` is **unset** (e.g. local Next dev with mock routes only), the feed stays **Demo** sample data. Rebuild the dashboard image after changing WebSocket or API URL env vars.

## Neo4j Browser: querying the graph

Relationship **types** in Cypher are **not** stored as a property named `type` on the relationship. Use the function **`type(r)`**, or bind the relationship with a concrete type in the pattern.

**Wrong** (triggers “property key … type … not in the database”):

```cypher
MATCH (n)-[r]->(m)
WHERE r.type IN ['CONTRADICTS', 'TRADED']
RETURN n, r, m LIMIT 50
```

**Right** — filter by relationship type:

```cypher
MATCH (n)-[r]->(m)
WHERE type(r) IN ['CONTRADICTS', 'CONTAINS', 'FILED', 'ABOUT', 'MADE']
RETURN n, r, m LIMIT 50
```

This project’s graph-builder does **not** create a **`TRADED`** relationship; insider trades may live only in Postgres. Contradiction edges use **`CONTRADICTS`** and store **`severity`**, **`similarity`**, etc. on **`r`**, e.g. `r.severity`.

**Simpler** — only contradiction links between claims:

```cypher
MATCH (a:Claim)-[r:CONTRADICTS]->(b:Claim)
RETURN a, r, b LIMIT 50
```

If this returns **no rows**, the Browser DB may be empty or the **graph-builder** has not synced yet; confirm **`docker compose`** includes **`neo4j`** and **`graph-builder`**, and check logs: **`docker compose logs graph-builder`**.

## `/api/v1/contradictions/latest` returning 500

If Swagger shows **500** for this route, it was often **response validation** (e.g. `entities` JSONB not matching a strict `dict` type, or numeric types from Postgres). The API schemas coerce **scores** and allow flexible **`entities`** so valid DB rows serialize without error. Rebuild the **api-server** image after pulling changes: **`docker compose up --build api-server`**.

## Contradiction agent (5.2) — tool calls in logs

The **contradiction-detector** runs an explicit **tool pipeline** (Python functions), not a cloud “Claude/GPT-4” router. The **LLM** (Ollama) is only used for the final **narrative** (`agent_reasoning`), with a **tool digest** appended to the prompt.

**Tools (see `services/contradiction-detector/src/agent_tools.py`):**

| Tool | Role |
|------|------|
| `semantic_compare` | Vector similarity + topic/entity overlap heuristics |
| `check_negation` | NLI cross-encoder (`check_negation` → `score_pairs`) |
| `temporal_check` | Date ordering and gap |
| `get_insider_context` | Postgres `insider_transactions` between claim dates (skipped if dates missing) |
| `severity_score` | Severity bucket + optional insider escalation |

**How to watch it live:**

```bash
docker compose logs -f contradiction-detector
```

Grep-friendly prefixes:

- **`[AGENT]`** — session start / decisions  
- **`[AGENT_TOOL]`** — one line per tool with a JSON summary of outputs  

**Orchestration note:** Tools run in a fixed order after candidate retrieval; **`get_insider_context`** only runs if NLI clears the contradiction threshold (saves DB I/O). To use **Claude/GPT-4** with native tool-calling, you would add API keys and a separate client — this repo uses **Ollama** for the prose step by default.
