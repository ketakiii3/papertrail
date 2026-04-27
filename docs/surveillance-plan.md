# Surveillance Module — Build Plan & Decision Log

**Companion to:** `surveillance-prd.md`
**Status:** Draft — awaiting approval
**Started:** 2026-04-26

This file is the running log of *how* the surveillance module gets built: ordered steps, decisions made along the way, problems hit, and how each was resolved. Append-only — do not rewrite history.

---

## Step-by-step plan

### Phase A — Event-bus foundation (Kafka + Celery)

#### M0a — Redpanda + kafka_client ✅ 2026-04-26
- [x] Added `redpanda` service to `docker-compose.yml` (dev-container mode, internal `:9092`, external `:19092`, `+:9644` admin).
- [x] Appended `aiokafka>=0.11` to all 6 service requirements.
- [x] Added `KAFKA_BOOTSTRAP_SERVERS` to `shared/config.py` (default `redpanda:9092`).
- [x] `shared/kafka_client.py`: `get_producer`, `publish(topic, payload, key)`, `consume(topic, group_id, handler)` with manual commit (at-least-once delivery; handlers must be idempotent).
- [x] Smoke test `scripts/kafka_smoke.py` roundtripped 5 messages through Redpanda.

#### M0b — Migrate existing producers/consumers ✅ 2026-04-26
- [x] `edgar-ingester`: produces `filing.new` via `kafka_client.publish`.
- [x] `transcript-ingester`: same swap for `filing.new`.
- [x] `claim-extractor`: Kafka consumer on `filing.new` (group `claim-extractors`); produces `claims.extracted`.
- [x] `contradiction-detector`: Kafka consumer on `claims.extracted` (group `contradiction-detectors`); produces `contradiction.found`.
- [x] `graph-builder`: two concurrent Kafka consumers via `asyncio.gather` on `claims.extracted` and `contradiction.found` (group `graph-builders`).
- [x] `api-server`: refactored WS to a single background Kafka consumer (group `api-ws-fanout`, `auto_offset_reset=latest`) that broadcasts to all connections via `ConnectionManager.broadcast`.
- [x] Added `redpanda: { condition: service_healthy }` to depends_on for all 6 services.
- [x] `redis_client.py` left in place (still used for caching + future Celery broker); no callers of `publish_event` remain.
- [x] Verified end-to-end: edgar-ingester pulled 11 new filings → claim-extractor processed (e.g. filing 229 → 4 claims) → contradiction-detector ran agent on PG claim pairs → graph-builder consuming both topics. `rpk topic list` shows `filing.new`, `claims.extracted`, `contradiction.found` all auto-created.

**Topic naming note:** kept original Redis stream names (`claims.extracted`, `contradiction.found`) instead of PRD's `claim.new` / `contradiction.new` to avoid renaming churn. PRD §4.2 should be read as those names.

#### M0c — Celery scaffold ✅ 2026-04-26
- [x] `shared/celery_app.py` — Celery app, broker+backend=Redis, default queue `surveillance`, `task_acks_late=True`, `worker_prefetch_multiplier=1` (right defaults for slow yfinance tasks).
- [x] `services/surveillance/` skeleton: Dockerfile, requirements.txt, `src/__init__.py`, `src/tasks.py` with dummy `add` task.
- [x] `celery-worker` service in compose (built from `services/surveillance/Dockerfile`, runs `celery -A shared.celery_app worker -l info -Q surveillance`).
- [x] `flower` service on `:5555` (same image, runs `celery flower`).
- [x] Smoke test: `add.delay(2,3).get(timeout=10) == 5`, state SUCCESS. Flower UI returns HTTP 200, worker log shows `Events of group {task} enabled by remote` confirming Flower→worker handshake.

### Phase B — Surveillance feature

#### M1 — Schema ✅ 2026-04-26
- [x] Added `surveillance_flags` table + 2 indexes to `infra/init.sql` (PRD §4.1 DDL).
- [x] Applied to live Postgres via `psql exec` (no data loss; existing 11 filings + claims preserved).
- [x] Added `CREATE CONSTRAINT FOR (i:Insider) REQUIRE i.name IS UNIQUE` to `Neo4jClient.setup_schema`; applied live via `cypher-shell` (constraint name `constraint_d6d16ee`).

#### M2 — Pure logic (no I/O) ✅ 2026-04-26
- [x] `event_study.py`:
  - `compute_market_model(stock_returns, market_returns)` — OLS, returns `MarketModelFit(alpha, beta, r2, residual_std, n_obs)`.
  - `compute_abnormal_returns(stock_df, market_df, event_date, ...)` — handles weekend roll-forward, baseline/event slicing, returns `EventStudyResult` with `daily_ar`, `car`, `car_zscore`, `volume_ratio`, or `insufficient_reason`.
- [x] `flagger.py`: `should_flag(result, z_threshold, volume_threshold)` returns `FlagDecision(flagged, reason)`. Reads `SURV_CAR_Z_THRESHOLD` (default 2.0) and `SURV_VOLUME_THRESHOLD` (default 1.5) from env.
- [x] 8 unit tests, all passing: market-model α/β recovery; rejects too-little-data; flat data → unflagged + small CAR; injected anomaly → flagged with z>3; insufficient history; incomplete event window; event date past data end; weekend → next-Monday roll-forward.

#### M3 — Wiring ✅ 2026-04-26
- [x] `market_data.py`: `fetch_ohlcv(ticker, start, end)` via yfinance with Redis cache (key `ohlcv:{ticker}:{start}:{end}`, TTL 24h). Cache hit shaved task from 1.3s → 0.46s on the second smoke run. `fetch_event_window` pulls 60 calendar days before / 15 after to safely cover the trading-day window.
- [x] `tasks.py`: `compute_event_study(transaction_id)` Celery task — joins `insider_transactions` + `companies` for ticker, idempotent via `surveillance_flags.transaction_id` UNIQUE, defers 2 days via `self.retry(countdown=...)` on `event_window_incomplete`, persists insufficient cases with `flag_reason` instead of crashing. Uses `psycopg2` (sync) since Celery prefork pool is sync.
- [x] `publisher.py`: `publish_flag_sync(payload)` spins up a short-lived event loop to call `kafka_client.publish` — works fine for low-frequency surveillance events.
- [x] `consumer.py`: Kafka consumer on `insider.new` (group `surveillance`); enqueues `compute_event_study.delay(transaction_id)`. Lightweight by design.
- [x] Two new compose services: `surveillance` (consumer) and `celery-worker` (already present, registered the new task on rebuild).
- [x] Hooked `edgar-ingester/src/form4_parser.py` to `RETURNING id` and publish `insider.new` after each successful Form 4 insert.
- [x] **End-to-end smoke verified twice** with seeded AAPL transactions:
  - txn 1 (Tim Cook 2024-08-15 sale): CAR=-1.51%, z=-0.55, vol_x=0.71, β=1.039, R²=0.558, not flagged.
  - txn 2 (2025-04-04, "tariff Friday"): vol_x=2.61 above threshold but z=-0.25 — market model correctly attributed price move to broader market action, not flagged. Exactly the behavior an event study should exhibit.
- [x] `surveillance.flag` topic verified via `rpk topic consume` — payload includes ticker, insider_name, transaction_type, CAR, z, vol_ratio, flagged, flag_reason.

#### M4 — Graph edges ✅ 2026-04-26
- [x] `Neo4jClient.upsert_insider_traded` and `Neo4jClient.upsert_anomalous_movement` added to `services/graph-builder/src/graph.py`. Both keyed by `transaction_id` so MERGE is idempotent across redelivery.
- [x] graph-builder consumer extended from 2 → 4 concurrent Kafka subscriptions via `asyncio.gather`: `claims.extracted`, `contradiction.found`, `insider.new`, `surveillance.flag`.
- [x] `insider.new` handler enriches via Postgres join (transaction_id → insider_name, ticker, shares, price, etc.) before MERGE.
- [x] `surveillance.flag` handler short-circuits when `flagged=false` so only real anomalies become graph edges.
- [x] Verified in Neo4j: `MATCH (i:Insider)-[r:TRADED]->(c:Company)` returns 2 rows (Tim Cook + Test Insider → AAPL); `MATCH (i:Insider)-[r:ANOMALOUS_MOVEMENT]->(c:Company)` returns 1 row (Demo Anomaly with CAR=0.087, z=2.7, vol=2.3).

#### M5 — API + dashboard ✅ 2026-04-26
- [x] `services/api-server/src/routers/surveillance.py` mounted at `/api/v1/surveillance`:
  - `GET /flags?flagged=&ticker=&limit=50` — joined with companies + insider_transactions.
  - `GET /flags/{id}` — includes `daily_ar`, `baseline_alpha`, `baseline_beta`, `baseline_r2`.
- [x] WS fan-out extended to consume **two** Kafka topics in parallel (`contradiction.found` + `surveillance.flag`) and broadcast as `type="surveillance"` for the new event type.
- [x] `dashboard/src/components/SurveillancePanel.tsx`: table with ticker, insider, BUY/SELL pill, CAR (color-coded), z, vol×, flagged badge. Click-through opens a drawer with α/β/R² stats and a 3-line recharts plot (AR, realized return, expected return) with reference line at 0.
- [x] Panel mounted in `dashboard/src/app/page.tsx` between Charts and Contradictions Feed.
- [x] Verified: list endpoint returns 2 rows, detail endpoint returns 6 daily AR entries with α=0.000677 β=1.039 R²=0.558. Dashboard HTTP 200, clean Next.js logs.
- [ ] **Skipped for v1** (deferred to M6 if time): standalone insider transaction timeline component with anomaly overlay. The drawer's daily-AR chart already serves the "look at one event" need; a separate timeline view becomes useful once you have many flagged events to compare.

**Caveat:** Dashboard renders without TS or runtime errors but I have not visually verified the styling. Open `http://localhost:3000` to eyeball.

#### M6 — Backfill + polish
- [ ] `services/surveillance/src/backfill.py`: select all `insider_transactions` with no flag row, enqueue `compute_event_study.delay(id)`.
- [ ] Tune thresholds against backfill: target ~5–15% flagged. Adjust `SURV_CAR_Z_THRESHOLD` / `SURV_VOLUME_THRESHOLD`.
- [ ] README: "Architecture" section update (Kafka + Celery), "Surveillance module" section.
- [ ] Screenshots of Flower dashboard + flagged-transactions panel for the GitHub README.

---

## Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-04-26 | New `surveillance` service vs. inlining into `edgar-ingester` | Keep ingester fast & failure-isolated; event-study has different deps (pandas, statsmodels) and runtime profile (CPU + network). |
| 2026-04-26 | Redis Streams pub/sub, **not Celery** | Matches existing PaperTrail pattern (`shared/redis_client.publish_event`). Adding Celery would mean a broker, worker, and beat container for no functional gain. |
| 2026-04-26 | `t = 0` is `transaction_date`, not `filing_date` | Insider actually traded on `transaction_date`; that's when info-leakage / informed-trading effect would appear in the tape. `filing_date` is up to 2 business days later. |
| 2026-04-26 | Market model (single-factor SPY) for v1, not Fama-French | Simplest defensible methodology; FF adds 2–4 factor data dependencies for marginal accuracy at this scale. Upgrade path is clean. |
| 2026-04-26 | Defer when event window incomplete rather than partial-window flag | Prevents look-ahead bias and keeps stored CAR comparable across rows. |
| 2026-04-26 | **Reversed:** add Kafka + Celery (was: keep Redis Streams only) | Resume claims "Kafka, Celery, Docker" event-driven microservices. Architecture must match the resume to be defensible in interviews. Cost: ~1.5 extra days of migration work. |
| 2026-04-26 | Use **Redpanda** instead of Kafka+Zookeeper for local | Single binary, Kafka API-compatible, no JVM, no Zookeeper. Resume says "Kafka" — Redpanda speaks the Kafka protocol, so the claim holds. Avoids 2 extra heavy containers in dev. |
| 2026-04-26 | Celery broker = Redis (existing), not RabbitMQ | Redis already in stack; adding RabbitMQ means another container for no functional gain at this scale. Redis broker is officially supported by Celery. |
| 2026-04-26 | Split surveillance into **two containers** (Kafka consumer + Celery worker) | The whole point of Celery is decoupling consumption from compute. Co-locating them defeats observability of backpressure and retries. |
| 2026-04-26 | `TRADED` edge written by graph-builder consuming `insider.new`, not by edgar-ingester directly | Single writer to Neo4j (graph-builder) keeps connection management and schema concerns in one service. Matches existing pattern for `CONTRADICTS`. |
| 2026-04-26 | `Insider` node keyed by `name` only (UNIQUE constraint) for v1 | Simplest. Known limitation: same-name insiders at different companies collide. Acceptable for demo; flagged as risk in PRD §4.4. |
| 2026-04-26 | **Approved by user**: Redpanda + Phase A before Phase B | Execution begins at M0a. |

---

## Problem log

*(Append entries as they happen. Format: date, problem, root cause, fix.)*

### 2026-04-26 — Form 4 ingester broken (pre-existing, not blocking surveillance)
**Problem:** `Form4Ingester.ingest_company_form4` fails for every recent MSFT filing with 404s on URLs like `https://data.sec.gov/Archives/edgar/data/0000789019/000078901926000021/xslF345X05/form4.xml`. As a result, `insider_transactions` was empty when M3 surveillance came online.
**Root cause:** `form4_parser.fetch_form4_filings` constructs the XML URL with a hardcoded `xslF345X05/` path that no longer matches SEC's current Form 4 layout (and possibly the host changed from `www.sec.gov` to `data.sec.gov`).
**Fix:** Out of scope for the surveillance milestones — logging here so we don't lose track. M6 (or a separate ticket) needs to: parse the filing index page to discover the actual Form 4 XML URL rather than assuming a fixed suffix. For M3 smoke verification I seeded synthetic AAPL transactions directly into Postgres + published `insider.new` manually, which proved the surveillance pipeline works end-to-end.

### 2026-04-26 — `scripts/` not visible inside service containers
**Problem:** `docker compose run --rm --no-deps edgar-ingester python -m scripts.kafka_smoke` failed with `ModuleNotFoundError: No module named 'scripts'`.
**Root cause:** Service Dockerfiles only `COPY services/<x>/src/` and `shared/`. `scripts/` is a dev-only directory not built into any image, and compose only mounts `./shared:/app/shared`.
**Fix:** Bind-mount it for one-off runs: `docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" edgar-ingester python -m scripts.kafka_smoke`. Don't bake `scripts/` into images — it's not runtime code.
