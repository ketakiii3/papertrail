# PaperTrail — Project Context for Claude

PaperTrail is a microservices pipeline that ingests SEC filings for S&P 500 names, extracts structured **claims** with NLP, detects **contradictions** between claims (pgvector similarity + NLI cross-encoder + an agent-tool pipeline), enriches with **insider Form 4** context, runs **event-study trade surveillance** (CAR + volume anomaly) on insider transactions, mirrors everything to a **Neo4j** knowledge graph, and serves it through a **FastAPI** backend and a **Next.js 14** dashboard with a live WebSocket feed.

This document is the working context for future Claude sessions: what has been built, how it fits together, and what is still open.

---

## 1. High-level architecture

```
              ┌────────────────────┐
              │   SEC EDGAR / yfinance / Ollama
              └─────────┬──────────┘
                        │
   ┌────────────────────┼──────────────────────────────┐
   │                    │                              │
edgar-ingester    transcript-ingester              (Form 4 path)
   │  filing.new       │  filing.new                 │ insider.new
   └────────┬──────────┘                              │
            ▼                                         │
       claim-extractor  ──claims.extracted──►  contradiction-detector
                                                 │ contradiction.found
            ┌────────────────────────────────────┴──────────────┐
            ▼                                                   ▼
        graph-builder (Neo4j)                              api-server
            ▲                                          (REST + WS fanout)
            │                                                   ▲
            │                                                   │
   surveillance.flag ◄──── celery-worker ◄── surveillance (Kafka→Celery)
                              (event-study)                     │
                                                                │
                                                            dashboard
                                                          (Next.js :3000)
```

### Containers (docker-compose.yml)

| Service | Purpose |
|---|---|
| `postgres` (pgvector/pg16) | Source of truth — companies, filings, claims (`vector(384)` embedding), contradictions, insider_transactions, surveillance_flags, watchlist |
| `redis` | Cache (yfinance OHLCV, embedding query) + Celery broker/backend |
| `neo4j` (5-community) | Knowledge graph: Company, Filing, Claim, Topic, Person, Insider |
| `redpanda` | Kafka-API broker (single binary, no JVM) for inter-service events |
| `ollama` | Local LLM (default `tinyllama`) for agent reasoning narratives |
| `edgar-ingester` | Pulls 10-K/10-Q/8-K filings + Form 4 insider transactions, publishes `filing.new` / `insider.new` |
| `transcript-ingester` | Pulls 8-K EX-99.1 exhibits as earnings/press transcripts → `filing.new` |
| `claim-extractor` | filing.new → sectionize → sentences → claim filter → FinBERT sentiment → entities → all-MiniLM-L6-v2 embedding → DB → `claims.extracted` |
| `contradiction-detector` | claims.extracted → pgvector neighbor search → NLI cross-encoder → agent tool pipeline (semantic / NLI / temporal / insider / severity) → Ollama narrative → DB → `contradiction.found` |
| `graph-builder` | 4 concurrent Kafka consumers (`claims.extracted`, `contradiction.found`, `insider.new`, `surveillance.flag`) → Neo4j MERGE upserts |
| `surveillance` | Kafka consumer on `insider.new` → enqueues Celery `compute_event_study` |
| `celery-worker` | Runs event-study tasks; persists `surveillance_flags`; publishes `surveillance.flag` |
| `flower` | Celery UI on `:5555` |
| `api-server` | FastAPI on `:8000` — REST + a single background task that consumes `contradiction.found` and `surveillance.flag` and fans out to all WS clients at `/ws/feed` |
| `dashboard` | Next.js 14 (App Router) on `:3000` |

### Kafka topics (Redpanda)

| Topic | Producer(s) | Consumer group(s) |
|---|---|---|
| `filing.new` | edgar-ingester, transcript-ingester | `claim-extractors`, `graph-builders` |
| `claims.extracted` | claim-extractor | `contradiction-detectors`, `graph-builders` |
| `contradiction.found` | contradiction-detector | `graph-builders`, `api-ws-fanout` |
| `insider.new` | edgar-ingester (Form 4) | `surveillance`, `graph-builders` |
| `surveillance.flag` | celery-worker | `graph-builders`, `api-ws-fanout` |

Note: topic names diverge from the PRD spec (`claim.new`/`contradiction.new`) — original Redis-stream names were kept (`claims.extracted` / `contradiction.found`) to avoid migration churn. Delivery is at-least-once with manual commits; handlers must be idempotent.

---

## 2. Repository layout

```
papertrail/
├── README.md                       # Quick-start + architecture summary
├── docker-compose.yml              # All 14 services
├── infra/init.sql                  # Postgres schema (pgvector + 7 tables)
├── shared/                         # Cross-service Python utilities
│   ├── config.py                   # Settings object (env-driven)
│   ├── db.py                       # asyncpg pool + query helpers
│   ├── kafka_client.py             # aiokafka producer/consumer wrappers
│   ├── celery_app.py               # Celery app (broker=Redis, queue=surveillance)
│   ├── redis_client.py             # Async Redis (cache only; publish_event unused)
│   ├── llm.py                      # Ollama client (generate_reasoning, ensure_model_available)
│   └── models.py                   # Pydantic data models
├── services/
│   ├── edgar-ingester/             # EDGAR + Form 4 pull
│   │   src/{main,ingester,edgar_client,form4_parser,sp500}.py
│   ├── transcript-ingester/        # 8-K EX-99.1 transcripts
│   ├── claim-extractor/            # Splitter, claim filter, FinBERT, embedder, NER
│   ├── contradiction-detector/     # Detector loop + agent + agent_tools + NLI
│   ├── graph-builder/              # Neo4j sync, 4 Kafka consumers via asyncio.gather
│   ├── api-server/                 # FastAPI routers: companies, search, watchlist, filings, surveillance, ws
│   └── surveillance/               # Event-study module
│       ├── src/{consumer,tasks,event_study,flagger,market_data,publisher}.py
│       └── tests/test_event_study.py  (8 unit tests)
├── dashboard/                      # Next.js 14 + TS + Tailwind + recharts
│   ├── src/app/{page,layout,globals.css,api/v1/...}    # / dashboard + mock fallback routes
│   ├── src/components/             # SearchBar, StatsCards, ContradictionCard,
│   │                                 SeverityChart, LiveFeed, SurveillancePanel,
│   │                                 Timeline, SeverityBadge
│   └── src/lib/api.ts              # Typed API client
├── scripts/kafka_smoke.py          # Roundtrip 5 messages through Redpanda
├── tests/                          # 3 standalone unit tests (severity, splitter, transcript_parser)
└── docs/
    ├── docker-dashboard-notes.md   # URL map, NEXT_PUBLIC_* gotchas, Ollama OOM tips, Neo4j queries
    ├── surveillance-prd.md         # Surveillance + event-bus + graph PRD (approved)
    ├── surveillance-plan.md        # Build log, decision log, problem log, M6 plan
    ├── security-audit.md           # Code audit vs ~/SECURITY_CHECKLIST.md (2026-05-21)
    └── next-steps.md               # ⭐ "open me first" checklist when resuming work
```

---

## 3. Data model (Postgres)

All in `infra/init.sql`. Key tables:

- **companies** — ticker, name, cik (unique), sector, industry, sp500 flag
- **filings** — accession_number (unique), form_type, filed_at, period_of_report, url, `raw_text` (full text dump), processed flag
- **claims** — filing_id, company_id, claim_text, claim_type, topic, sentiment, confidence, `entities jsonb`, temporal_ref, source_section, `embedding vector(384)`, claim_date
- **contradictions** — claim_a_id, claim_b_id, similarity_score, nli_contradiction_score, severity, time_gap_days, explanation (rule-based), agent_reasoning (Ollama)
- **insider_transactions** — insider_name/title, transaction_type (buy/sell), shares, price, total_value, transaction_date, filing_date
- **surveillance_flags** — UNIQUE on transaction_id, CAR, car_zscore, volume_ratio, baseline α/β/R², `daily_ar jsonb`, flagged, flag_reason
- **watchlist** — email + ticker (composite unique)

Postgres extension `vector` is required; `pgvector/pgvector:pg16` provides it. Embeddings are 384-dim from `all-MiniLM-L6-v2`.

---

## 4. The agent tool pipeline (contradiction detector)

`services/contradiction-detector/src/agent.py` orchestrates explicit tools in `agent_tools.py`. Visible logs are prefixed `[AGENT]` and `[AGENT_TOOL]`. Per pair:

1. `semantic_compare(ca, cb, cosine)` — topic overlap + shared-entity hits + short summary
2. `check_negation(text_a, text_b)` — cross-encoder NLI (`cross-encoder/nli-deberta-v3-base`), softmax → {contradiction, entailment, neutral}. Below `NLI_CONTRADICTION_THRESHOLD = 0.6` → bail out
3. `temporal_check(ca, cb)` — gap in days, b-after-a ordering
4. `get_insider_context` — pulls Form 4 rows between the two claim dates and rolls them up via `summarize_insider_rows` (counts sells, sums notional, marks `large_insider_sales` if ≥$500k or ≥3 sells)
5. `severity_score(...)` — base severity from `classify_severity()` (weighted NLI + similarity + recency boost), escalated one bucket on `large_insider_sales`
6. `generate_reasoning(...)` — Ollama produces a 2–3 sentence analyst narrative using the full tool digest

The older claim becomes A, newer is B (so "B contradicts what A said earlier").

---

## 5. Surveillance / event study

See `docs/surveillance-prd.md` (PRD, approved) and `docs/surveillance-plan.md` (running build log).

**Methodology** (`event_study.py`):
- t=0 = insider `transaction_date`, rolled forward to next trading day
- Baseline T1 = `[-30, -2]` trading days (gap day −1 excluded)
- Event window T2 = `[0, +5]` trading days
- Market model: OLS `r_i = α + β·r_m + ε` fit on T1 (SPY as `SURV_MARKET_INDEX`)
- `AR_t = r_i,t − (α + β·r_m,t)`; `CAR = Σ AR_t`; `z = CAR / (σ_AR · √N)`
- `vol_ratio = mean(Vol on T2) / mean(Vol on T1)`
- Flag if `|z| > SURV_CAR_Z_THRESHOLD (2.0)` AND `vol_ratio > SURV_VOLUME_THRESHOLD (1.5)`

Edge cases: insufficient_history, event_window_incomplete (Celery `self.retry(countdown=2d)`), event_date_after_data_end, market_data_unavailable → persisted with `flagged=false` and a `flag_reason`.

OHLCV is fetched once per (ticker, start, end) via `yfinance` and cached in Redis 24h (`SURV_PRICE_CACHE_TTL`).

---

## 6. Knowledge graph (Neo4j)

Driver: official `neo4j` Python (sync). `graph.py:Neo4jClient.setup_schema()` creates UNIQUE constraints on `Company.ticker`, `Filing.filing_id`, `Claim.claim_id`, `Topic.name`, `Insider.name`, plus indexes on dates.

Edges currently written:
- `(:Company)-[:FILED]->(:Filing)`
- `(:Filing)-[:CONTAINS]->(:Claim)`
- `(:Claim)-[:ABOUT]->(:Topic)`
- `(:Person)-[:MADE]->(:Claim)` (only when claim has a speaker; transcripts only)
- `(:Claim)-[:CONTRADICTS]->(:Claim)` with `severity`, `similarity`, `nli_score`, `time_gap_days`
- `(:Insider)-[:TRADED {transaction_id}]->(:Company)` with date/type/shares/price/total_value
- `(:Insider)-[:ANOMALOUS_MOVEMENT {transaction_id}]->(:Company)` with car, car_zscore, vol_ratio, event_date (only when `flagged=true`)

All edges are MERGEd by a key that survives Kafka redelivery (e.g. `transaction_id`, `claim_id`).

Querying note (from `docs/docker-dashboard-notes.md`): use `type(r) IN [...]` in Cypher, not `r.type` — relationship types are not stored as properties.

---

## 7. API surface (FastAPI)

Lifespan: opens DB pool, Redis, spawns `start_ws_fanout()` (background Kafka→WS task), closes producer + pools on shutdown. CORS open.

- `GET /` → 302 `/docs`
- `GET /health`
- `GET /api/v1/companies` (search by ticker/name)
- `GET /api/v1/companies/{ticker}`
- `GET /api/v1/companies/{ticker}/timeline` (filings + contradictions merged, date-sorted)
- `GET /api/v1/companies/{ticker}/contradictions` (severity / topic filter)
- `GET /api/v1/companies/{ticker}/claims` (claim_type / topic / sentiment)
- `GET /api/v1/companies/{ticker}/filings/{id}/diff` (compares to previous same-form filing: new topics, sentiment changes on shared topics, risk-factor count delta)
- `GET /api/v1/companies/{ticker}/insiders` (joined with overlapping contradictions, flags `suspicious=true` when a sell sits between high/critical contradicting claim dates)
- `GET /api/v1/search/claims?q=...` (semantic via `SentenceTransformer.encode` → pgvector; falls back to ILIKE)
- `GET /api/v1/contradictions/latest`
- `GET /api/v1/stats`
- `POST/GET/DELETE /api/v1/watchlist`
- `GET /api/v1/surveillance/flags?flagged=&ticker=&limit=` (list)
- `GET /api/v1/surveillance/flags/{id}` (detail with α/β/R² and daily_ar)
- `WS /ws/feed` — broadcasts `{type: "contradiction" | "surveillance", data: ...}` and a 30s `ping`

---

## 8. Dashboard

Next.js 14 (App Router) + TS + Tailwind + recharts + SWR.

- `dashboard/src/app/page.tsx` — single-page layout: Hero → StatsCards → (SeverityChart + LiveFeed) → SurveillancePanel → Contradictions feed (severity filter)
- Mock-data fallback: when `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` are unset, the dashboard uses the built-in `src/app/api/v1/...` route handlers. This is the Vercel demo mode.
- `dashboard/src/components/SurveillancePanel.tsx` — table with ticker, insider, BUY/SELL pill, CAR (color-coded), z, vol×, flagged badge; row click opens a drawer with α/β/R² and a 3-line recharts plot (AR, realized return, expected return) plus a reference line at 0.
- Build-time gotcha: `NEXT_PUBLIC_*` are inlined at `npm run build`, so they must be passed as Compose `build.args` (already done). Browser cannot resolve internal Compose hostnames; use `localhost:8000` / `ws://localhost:8000`.

---

## 9. Environment variables (`.env.example`)

```
DATABASE_URL=postgresql://papertrail:papertrail@postgres:5432/papertrail
REDIS_URL=redis://redis:6379/0
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=papertrail123
EDGAR_USER_AGENT=PaperTrail research@papertrail.dev   # must be a real email-style UA per SEC
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=tinyllama                                # default for CPU/low RAM
API_HOST=0.0.0.0
API_PORT=8000
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
# (implicit; not in .env.example) KAFKA_BOOTSTRAP_SERVERS=redpanda:9092
# Surveillance tuning (defaults set in code):
# SURV_CAR_Z_THRESHOLD=2.0
# SURV_VOLUME_THRESHOLD=1.5
# SURV_BASELINE_DAYS=30
# SURV_EVENT_DAYS=5
# SURV_MARKET_INDEX=SPY
# SURV_PRICE_CACHE_TTL=86400
```

---

## 10. URLs / ports

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API + Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Neo4j Browser | http://localhost:7474 (`neo4j` / `papertrail123`) |
| Ollama | http://localhost:11434 |
| Flower (Celery UI) | http://localhost:5555 |
| Redpanda admin | http://localhost:9644 |
| Postgres | localhost:5432 (`papertrail`/`papertrail`) |
| Redis | localhost:6379 |

---

## 11. Running

```bash
cp .env.example .env
# set EDGAR_USER_AGENT to a real "Name email" string
docker compose up --build
docker compose exec ollama ollama pull tinyllama   # one-time

# Tail agent tool logs
docker compose logs -f contradiction-detector

# Dashboard-only (mock data)
cd dashboard && npm install && npm run dev
```

Useful one-offs:

```bash
# Kafka smoke test
docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" \
  edgar-ingester python -m scripts.kafka_smoke

# Inspect topics
docker compose exec redpanda rpk topic list
docker compose exec redpanda rpk topic consume surveillance.flag --num 5

# Surveillance unit tests
docker compose run --rm --no-deps celery-worker pytest surveillance/tests -q
```

---

## 12. Completed milestones (per `docs/surveillance-plan.md`)

| Phase | Milestone | Status |
|---|---|---|
| A | M0a — Redpanda + `shared/kafka_client.py` + smoke test | ✅ 2026-04-26 |
| A | M0b — All 6 services migrated off Redis Streams to Kafka | ✅ 2026-04-26 |
| A | M0c — Celery + Flower scaffold; `add.delay(2,3).get() == 5` | ✅ 2026-04-26 |
| B | M1 — `surveillance_flags` table + `Insider.name` constraint | ✅ 2026-04-26 |
| B | M2 — Pure `event_study.py` + `flagger.py` + 8 unit tests | ✅ 2026-04-26 |
| B | M3 — Wiring: `market_data.py` (yfinance + Redis cache), `tasks.py`, `consumer.py`, `publisher.py`, Form 4 → `insider.new` | ✅ 2026-04-26 |
| B | M4 — Neo4j `TRADED` + `ANOMALOUS_MOVEMENT` edges; graph-builder now 4-way consumer | ✅ 2026-04-26 |
| B | M5 — `/api/v1/surveillance/flags*`, WS fanout for surveillance, dashboard `SurveillancePanel` + drawer chart | ✅ 2026-04-26 |
| B | M6 — Backfill script + README rewrite + stale-doc fixes + dead-code removal | ✅ 2026-05-21 (threshold tuning + screenshots + visual verification still owed by user) |

End-to-end was last verified 2026-04-26 with two seeded AAPL transactions (Tim Cook 2024-08-15 sell, plus a 2025-04-04 "tariff Friday" sell). Both produced sensible market-model fits (α≈0.0007, β≈1.04, R²≈0.56), correctly *not* flagged because z was inside threshold even when volume spiked — the model attributed the move to broader market action. Neo4j confirmed TRADED edges for Tim Cook + a Test Insider, and one ANOMALOUS_MOVEMENT edge from a Demo Anomaly row (CAR=0.087, z=2.7, vol=2.3).

---

## 13. What is still open / known gaps

### Closed in 2026-05-21 pass

- `services/surveillance/src/backfill.py` exists. CLI: `--limit`, `--ticker`, `--dry-run`, `--overwrite` (overwrite deletes existing flag rows so retuned thresholds re-populate cleanly). Invocation pattern documented in the file's module docstring and in the README "Run the backfill" block.
- README rewritten: architecture table covers all 7 service rows; new "Event bus & async compute" topic table; new "Surveillance module" + "Threshold tuning" sections with the SQL query and env vars; Flower (`:5555`) and Redpanda admin (`:9644`) added to the URL table.
- `docs/docker-dashboard-notes.md` updated: removed stale "graph-builder does not create a `TRADED` relationship" claim, added `TRADED` and `ANOMALOUS_MOVEMENT` to the Cypher example, fixed the Live Feed paragraph to reference Kafka (not Redis).
- Dead code removed: `shared/redis_client.publish_event`, `create_consumer_group`, `consume_events` deleted. `shared/redis_client.py` now documents itself as cache-only; `shared/kafka_client.py` docstring no longer references the dead Redis function.

### Still owed (user-blocked, cannot run from a Claude session)

1. **Threshold tuning run.** User needs to run `docker compose run --rm --no-deps surveillance python -m surveillance.backfill --dry-run`, then without `--dry-run`, then check `SELECT COUNT(*) FILTER (WHERE flagged) * 1.0 / NULLIF(COUNT(*),0) FROM surveillance_flags` against the 5–15% band, adjust `SURV_CAR_Z_THRESHOLD` / `SURV_VOLUME_THRESHOLD` in `.env`, and re-run with `--overwrite`. Record the final chosen thresholds + observed flag rate in the `docs/surveillance-plan.md` decision log.
2. **Screenshots** for the README: `docs/img/flower.png` (Flower with at least one SUCCESS task) and `docs/img/surveillance-panel.png` (dashboard panel + drawer with AR chart).
3. **Visual verification of dashboard.** M5 caveat: the panel renders without TS/runtime errors but layout was never eyeballed live. Open `http://localhost:3000` after `docker compose up`.
4. **Form 4 ingester real-CIK verification.** `form4_parser.fetch_form4_filings` no longer hardcodes `xslF345X05/` — it uses `primaryDocument` from EDGAR submissions JSON. Code-level fix is in, but no real (non-seeded) end-to-end run is documented yet. Run `docker compose exec edgar-ingester python -c "import asyncio; from src.form4_parser import run_form4_ingestion; asyncio.run(run_form4_ingestion())"` against a real S&P 500 CIK and confirm `insider_transactions` rows appear, then `surveillance.flag` events follow.
5. **Optional `InsiderTimeline.tsx`** — deferred indefinitely (drawer already covers the single-event view; only worth it once many flagged events exist to compare).

### Other small things

- `tests/` (root) has 3 tests for `severity_scorer`, `splitter`, `transcript_parser`. `services/surveillance/tests/test_event_study.py` has 8 tests. There is no top-level test runner / CI config.
- No license file.
- `scripts/` is dev-only (not baked into images); must be bind-mounted to run.
- Dashboard has a `vercel.json` but no Vercel deploy is documented in the repo.

---

## 14. Key decisions (from `docs/surveillance-plan.md` decision log)

- **Redpanda over Kafka+Zookeeper** for local dev — single binary, Kafka API-compatible, no JVM. Resume-defensible because Redpanda speaks the Kafka protocol.
- **Celery broker = Redis**, not RabbitMQ — Redis is already in the stack.
- **Surveillance split into two containers** (`surveillance` Kafka consumer + `celery-worker` compute) — the whole point of Celery is decoupling backpressure from intake.
- **`Insider` keyed by `name` only.** Known collision risk across same-name insiders at different companies; acceptable for v1, flagged in PRD §4.4.
- **`t = 0` = `transaction_date`**, not `filing_date` — that's when the insider actually traded.
- **Market model (single-factor SPY)**, not Fama-French — simplest defensible methodology at this scale.
- **Defer (Celery retry with countdown)** when the event window hasn't elapsed, rather than partial-window flagging — avoids look-ahead bias.
- **Single Neo4j writer** (graph-builder) for all node types, including TRADED/ANOMALOUS_MOVEMENT — keeps schema concerns in one place.

---

## 15. Security posture (post 2026-05-21 audit + Phase 1+2 patches)

Code audit performed against `~/SECURITY_CHECKLIST.md`, full report in `docs/security-audit.md`. PaperTrail's posture is "localhost-only demo, no auth, no PII" — most checklist items are N/A. Phase 1+2 hardening has shipped:

- **Infra ports** bound to `127.0.0.1:` only (postgres, redis, neo4j, redpanda, ollama, flower). Only `dashboard (:3000)` and `api-server (:8000)` are LAN-reachable.
- **CORS** is now env-driven (`CORS_ALLOWED_ORIGINS`, default `http://localhost:3000,http://localhost:8000`), `allow_credentials=False`, methods/headers narrowed. The dangerous `*` + `credentials=True` combo is gone.
- **Security headers** (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`) set via middleware in `services/api-server/src/main.py`. HSTS deliberately omitted until real TLS is in front.
- **Input** — `WatchlistRequest.email` is now `EmailStr`; `search?q=` capped at 200 chars.
- **LLM prompt** — user-controlled fields wrapped in `<claim_a>`, `<claim_b>`, `<company>`, `<tool_trace>` tags. `_neutralize_tags()` in `shared/llm.py` strips those exact tags from untrusted input so a hostile filing can't escape the wrapper. Top-of-prompt instruction tells the model tagged content is data, not instructions.
- **`.env.example`** has a top SECURITY warning block.

Deferred (separate PRs, in priority order):

1. **Rate limiting** (`slowapi`, plus a cap on `ConnectionManager.active_connections`).
2. **Contradiction-detector → Celery for Ollama enrichment** — fixes the §15a backpressure finding. Same shape as the surveillance Celery refactor.
3. **Auth** — only when ever shipping multi-tenant. Watchlist endpoints are currently unauthenticated (`email` query param).
4. **Dependency pinning + CI audit** (`pip-compile`, `pip-audit`, `npm audit`).
5. **Form 4 real-CIK verification** (still open from M6).
6. **Threshold tuning + dashboard visual eyeball + screenshots** (M6 user-side items).

## 16. Local CLAUDE-specific notes

- Working directory: `/Users/ketaki.dabade/papertrail`. Git is clean on `main` at writing time; recent commits include the Docker UX + agent tool pipeline + Ollama integration + EDGAR/CPU fixes.
- When editing services, remember the import path quirk: each service Dockerfile copies `shared/` into `/app/shared/` and the service's own `src/` into `/app/src/` (or `/app/surveillance/` for the surveillance image). Files do `sys.path.insert(0, "/app")` at top of `main.py`.
- `services/surveillance/Dockerfile` is reused for both the Kafka-consumer container and the Celery worker (different `command:` in compose).
- The api-server's `lifespan` cancels the WS fanout task on shutdown — when adding new Kafka consumers there, plug them into `start_ws_fanout` rather than starting standalone tasks.
- Local LLM (Ollama) is *optional* for contradiction storage — `generate_reasoning` returns `None` if Ollama is unreachable and `agent_reasoning` simply ends up NULL. Don't gate the pipeline on LLM availability.
