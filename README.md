# PaperTrail

PaperTrail ingests SEC filings for S&P 500 names, extracts structured **claims**, detects **contradictions** between claims (pgvector similarity + NLI cross-encoder + an agent-tool pipeline), enriches with **insider (Form 4)** context, runs **event-study trade surveillance** (CAR + volume anomaly) on insider transactions, and exposes the results through a **FastAPI** backend and **Next.js** dashboard with a live WebSocket feed. A **Neo4j** graph mirrors claims, contradictions, and insider trade activity.

## Architecture (high level)

| Layer | Role |
|--------|------|
| **edgar-ingester** | Pulls 10-K/10-Q/8-K filings and Form 4 insider transactions from EDGAR. Emits `filing.new` and `insider.new`. |
| **transcript-ingester** | Pulls 8-K EX-99.1 exhibits (earnings press releases / transcripts). Emits `filing.new`. |
| **claim-extractor** | `filing.new` → sectionize → claim filter → FinBERT sentiment → entities → MiniLM embeddings → DB → `claims.extracted`. |
| **contradiction-detector** | `claims.extracted` → pgvector neighbor search → NLI → agent tool pipeline (semantic / NLI / temporal / insider / severity) → Ollama narrative → DB → `contradiction.found`. |
| **surveillance** + **celery-worker** | `insider.new` → Kafka consumer enqueues a Celery task that fetches OHLCV (yfinance, Redis-cached), fits a single-factor SPY market model on `[-30,-2]`, computes CAR and volume ratio on `[0,+5]`, persists to `surveillance_flags`, and emits `surveillance.flag`. |
| **graph-builder** | 4 concurrent Kafka consumers (`claims.extracted`, `contradiction.found`, `insider.new`, `surveillance.flag`) syncing into Neo4j with idempotent MERGE upserts. |
| **api-server** | FastAPI REST + a single background Kafka→WebSocket fanout broadcasting `contradiction.found` and `surveillance.flag` to all clients on `/ws/feed`. |
| **dashboard** | Next.js 14 UI at `:3000` (stats, contradictions feed, surveillance panel with α/β/R² drawer chart, live feed). |

## Event bus & async compute

Inter-service eventing runs on **Redpanda** (Kafka-API broker, single binary, no JVM). Redis is reserved for **caching** (yfinance OHLCV) and as the **Celery broker / result backend**.

| Topic | Producer(s) | Consumer group(s) |
|---|---|---|
| `filing.new` | edgar-ingester, transcript-ingester | `claim-extractors`, `graph-builders` |
| `claims.extracted` | claim-extractor | `contradiction-detectors`, `graph-builders` |
| `contradiction.found` | contradiction-detector | `graph-builders`, `api-ws-fanout` |
| `insider.new` | edgar-ingester (Form 4) | `surveillance`, `graph-builders` |
| `surveillance.flag` | celery-worker | `graph-builders`, `api-ws-fanout` |

Delivery is at-least-once with manual offset commit — handlers are idempotent (DB ON CONFLICT, Neo4j MERGE keyed on stable IDs).

Contradiction detection includes explicit **agent tools** (`semantic_compare`, `check_negation`, `temporal_check`, `get_insider_context`, `severity_score`) with log lines prefixed `[AGENT]` and `[AGENT_TOOL]` in the detector service. See `docs/docker-dashboard-notes.md` for URLs, Ollama sizing, Neo4j queries, and troubleshooting.

## Prerequisites

- **Docker** and **Docker Compose**
- For full ingestion: a valid **SEC EDGAR** user agent string (email-style) in `.env` per [SEC fair access](https://www.sec.gov/os/webmaster-faq#code-support)

## Quick start (full stack)

```bash
cp .env.example .env
# Edit .env: set EDGAR_USER_AGENT to something like "YourName contact@yourdomain.com"

docker compose up --build
```

Pull the configured Ollama model once (default is `tinyllama`, sized for CPU):

```bash
docker compose exec ollama ollama pull tinyllama
```

Then open:

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 (`neo4j` / `papertrail123`) |
| Ollama | http://localhost:11434 |
| Flower (Celery UI) | http://localhost:5555 |
| Redpanda admin | http://localhost:9644 |

## Surveillance module

The `surveillance` + `celery-worker` services flag insider Form 4 transactions whose surrounding price/volume action is statistically anomalous (event-study methodology in `docs/surveillance-prd.md` §6).

- **Baseline window** T1 = `[-30, -2]` trading days, excluding gap day −1.
- **Event window** T2 = `[0, +5]` trading days, with t=0 = `transaction_date` rolled forward to the next trading day.
- **Market model:** OLS `r_i = α + β·r_m + ε` on T1, with `SURV_MARKET_INDEX` (SPY) as benchmark.
- **Flag if:** `|z| > SURV_CAR_Z_THRESHOLD` (default 2.0) **AND** `vol_ratio > SURV_VOLUME_THRESHOLD` (default 1.5), where `z = CAR / (σ_AR · √N)` and `vol_ratio = mean(Vol on T2) / mean(Vol on T1)`.
- **Defers** (Celery retry, 2-day countdown) when the event window hasn't elapsed yet — no look-ahead bias.

Tuning knobs (all environment-driven):

| Var | Default | Meaning |
|---|---|---|
| `SURV_CAR_Z_THRESHOLD` | 2.0 | |z| flag threshold |
| `SURV_VOLUME_THRESHOLD` | 1.5 | volume ratio flag threshold |
| `SURV_BASELINE_DAYS` | 30 | trading days before event |
| `SURV_EVENT_DAYS` | 5 | trading days after event |
| `SURV_MARKET_INDEX` | SPY | benchmark ticker |
| `SURV_PRICE_CACHE_TTL` | 86400 | yfinance OHLCV cache TTL (s) |

### View flags

```bash
curl http://localhost:8000/api/v1/surveillance/flags?flagged=true
curl http://localhost:8000/api/v1/surveillance/flags/1   # detail with daily_ar + α/β/R²
```

Dashboard: the **Surveillance** panel on `/` shows the table; click a row for the drawer with the 3-line AR / realized / expected return chart.

### Run the backfill

`services/surveillance/src/backfill.py` replays event-study computation over existing `insider_transactions` rows that don't already have a `surveillance_flags` entry:

```bash
# preview what would be enqueued
docker compose run --rm --no-deps surveillance \
    python -m surveillance.backfill --dry-run

# enqueue them
docker compose run --rm --no-deps surveillance \
    python -m surveillance.backfill --limit 200

# retune thresholds: --overwrite deletes existing flag rows so they get recomputed
docker compose run --rm --no-deps surveillance \
    python -m surveillance.backfill --ticker AAPL --overwrite
```

Watch task progress at **http://localhost:5555** (Flower) or with `docker compose logs -f celery-worker`.

### Threshold tuning

After a backfill, check the flag rate and aim for the 5–15% band:

```sql
SELECT COUNT(*) FILTER (WHERE flagged) * 1.0 / NULLIF(COUNT(*), 0) AS flag_rate,
       COUNT(*) FILTER (WHERE flagged) AS flagged,
       COUNT(*) AS total
FROM surveillance_flags;
```

If outside the band, adjust `SURV_CAR_Z_THRESHOLD` / `SURV_VOLUME_THRESHOLD` in `.env`, then re-run with `--overwrite`.

## Dashboard only (mock API, no backend)

From `dashboard/`:

```bash
npm install
npm run dev
```

Leave `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` **unset** so the app uses built-in Next.js route handlers with sample data (`src/app/api/v1/...`).

## Viewing agent + tool logs

```bash
docker compose logs -f contradiction-detector   # [AGENT] and [AGENT_TOOL] lines
docker compose logs -f celery-worker            # surveillance event-study results
docker compose logs -f graph-builder            # Neo4j upserts
```

## Repository layout

```
├── dashboard/          # Next.js UI
├── services/
│   ├── edgar-ingester/         # 10-K/10-Q/8-K + Form 4 pull
│   ├── transcript-ingester/    # 8-K EX-99.1 exhibits
│   ├── claim-extractor/        # FinBERT + MiniLM pipeline
│   ├── contradiction-detector/ # Agent + tool pipeline
│   ├── surveillance/           # Event-study consumer + Celery tasks + backfill
│   ├── graph-builder/          # Neo4j sync (4 Kafka consumers)
│   └── api-server/             # FastAPI + WS fanout
├── shared/             # DB, Redis, Kafka, Celery, LLM helpers
├── infra/              # Postgres schema (init.sql)
├── scripts/            # Dev-only helpers (Kafka smoke test)
├── tests/              # Unit tests for severity, splitter, transcript parser
├── docs/               # PRDs, build plan, Docker / API notes
└── docker-compose.yml
```

## License

No license file is included in this repository; add one if you intend to distribute or accept contributions.
