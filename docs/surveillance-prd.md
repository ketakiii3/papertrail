# PaperTrail — Surveillance + Event Bus + Graph Edges PRD

**Status:** Draft — awaiting approval
**Owner:** Ketaki Dabade
**Last updated:** 2026-04-26

**Scope of this revision:** This PRD covers three coordinated changes:
1. **Event-study trade surveillance** (CAR + volume anomaly flagging on insider transactions).
2. **Event-bus migration** Redis Streams → **Kafka (Redpanda)** + **Celery** for async compute, to match the deployed architecture claimed on the resume.
3. **Knowledge-graph edges**: add `TRADED` (Insider → Company) and `ANOMALOUS_MOVEMENT` (Insider → Company). `CONTRADICTS` already exists in `services/graph-builder/src/graph.py:add_contradiction_edge`.

---

## 1. Problem & motivation

PaperTrail already ingests SEC Form 4 filings into the `insider_transactions` table, but it currently treats each transaction as a flat record. There is no signal for whether the surrounding price/volume action was *abnormal* — i.e., whether the insider's trade coincided with statistically unusual market behavior.

Adding an event-study surveillance layer gives PaperTrail the same shape of analysis that real exchange surveillance teams (NYSE, Nasdaq MarketWatch, FINRA) run daily: detect anomalous returns and volume around insider events, flag for review.

**Resume framing:** "Event-study-based trade surveillance flagging abnormal price/volume activity around insider transactions."

## 2. Scope

### In scope (v1)
- Pull daily OHLCV via `yfinance` for a `[-30, +10]` trading-day window around each Form 4 transaction date.
- Compute expected returns via a **market model** (OLS regression of stock returns on S&P 500 returns over the baseline window `[-30, -2]`).
- Compute **abnormal return (AR)** per day and **cumulative abnormal return (CAR)** over `[0, +5]`.
- Compute **volume ratio**: avg daily volume in `[0, +5]` ÷ avg daily volume in `[-30, -2]`.
- Flag a transaction when **|CAR| > 2σ** of baseline AR distribution **AND** volume ratio > 1.5×.
- Persist results to a new `surveillance_flags` table.
- Push flags to existing dashboard via the WebSocket / SSE feed.
- New Neo4j edge type `ANOMALOUS_MOVEMENT` linking `(:Insider)-[:ANOMALOUS_MOVEMENT {car, vol_ratio}]->(:Company)`.

### Out of scope (v1)
- Intraday data (minute bars).
- Multi-factor models (Fama-French 3/5, CAPM with risk-free rate).
- Cross-sectional studies across many insiders.
- Backfilling historic transactions (only newly ingested Form 4s; backfill is a separate manual job).
- Alerting / notifications outside the dashboard.

## 3. Users & UX

**Primary user:** Me (developer / demo audience).
**Surface:** New dashboard panel **"Flagged Insider Transactions"** showing a table:

| Ticker | Insider | Trade date | Type | Shares | CAR [0,+5] | Vol ratio | Sparkline |

Row click → drawer with the full daily AR series + price chart annotated with `t=0`.

## 4. Data model

### 4.1 New Postgres table

```sql
CREATE TABLE IF NOT EXISTS surveillance_flags (
    id              SERIAL PRIMARY KEY,
    transaction_id  INT NOT NULL REFERENCES insider_transactions(id) ON DELETE CASCADE,
    company_id      INT NOT NULL REFERENCES companies(id),
    event_date      DATE NOT NULL,
    car             NUMERIC(8,5) NOT NULL,           -- cumulative abnormal return [0,+5]
    car_zscore      NUMERIC(8,4) NOT NULL,           -- CAR normalized by baseline AR std
    volume_ratio    NUMERIC(8,4) NOT NULL,           -- post / baseline
    baseline_alpha  NUMERIC(10,6),
    baseline_beta   NUMERIC(10,6),
    baseline_r2     NUMERIC(6,4),
    daily_ar        JSONB NOT NULL,                  -- [{date, ar, ret, expected}]
    flagged         BOOLEAN NOT NULL,
    flag_reason     TEXT,
    computed_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (transaction_id)
);
CREATE INDEX IF NOT EXISTS idx_surveillance_flagged
    ON surveillance_flags(flagged, event_date DESC);
```

### 4.2 Kafka topics (replacing Redis Streams)

| Topic | Producer | Consumer(s) | Payload |
|---|---|---|---|
| `filing.new` | edgar-ingester, transcript-ingester | claim-extractor, graph-builder | `{filing_id, company_id, form_type, url}` |
| `insider.new` | edgar-ingester | surveillance, graph-builder | `{transaction_id, company_id, ticker, insider_name, transaction_date, type, shares, price}` |
| `claim.new` | claim-extractor | contradiction-detector, graph-builder | existing payload |
| `contradiction.new` | contradiction-detector | graph-builder, api-server (WS) | existing payload |
| `surveillance.flag` | surveillance (Celery worker) | graph-builder, api-server (WS) | `{transaction_id, ticker, car, car_zscore, volume_ratio, flagged, event_date}` |

Single Redpanda broker for dev. Topics auto-created with `partitions=1, replication=1` for local; document `partitions=3` for "prod" config.

### 4.3 Celery task

**Broker:** Redis (already in stack). **Result backend:** Redis.
**Task:** `surveillance.tasks.compute_event_study(transaction_id: int)` — idempotent (UNIQUE on `transaction_id`), retries 3× with exponential backoff on yfinance failure, defers (re-queues with countdown) if event window not yet elapsed.

### 4.4 Neo4j edges

**New edges added in this revision:**

```cypher
// Written by graph-builder consuming insider.new
MERGE (i:Insider {name: $name})
MERGE (c:Company {ticker: $ticker})
MERGE (i)-[r:TRADED {transaction_id: $transaction_id}]->(c)
SET r.transaction_date = $date, r.type = $type,
    r.shares = $shares, r.price = $price, r.total_value = $value

// Written by graph-builder consuming surveillance.flag (only when flagged=true)
MATCH (i:Insider {name: $name})
MATCH (c:Company {ticker: $ticker})
MERGE (i)-[r:ANOMALOUS_MOVEMENT {transaction_id: $transaction_id}]->(c)
SET r.car = $car, r.car_zscore = $z, r.volume_ratio = $vol,
    r.event_date = $event_date
```

**Existing edge inventory** (for reference, see `services/graph-builder/src/graph.py`):
`FILED`, `CONTAINS`, `ABOUT`, `MADE`, `CONTRADICTS`. New constraint:
`CREATE CONSTRAINT FOR (i:Insider) REQUIRE i.name IS UNIQUE` — note: name collisions across companies are possible; consider composite key `(name, primary_company_ticker)` if it becomes a real problem.

## 5. Architecture

### 5.0 Event-bus migration (cross-cutting)

Add to `docker-compose.yml`:
- **`redpanda`** service (Kafka API-compatible, single binary, no Zookeeper). Image: `redpandadata/redpanda:latest`. Exposed on `9092`.
- **`celery-worker`** service running surveillance tasks (image built from `services/surveillance/`). Command: `celery -A surveillance.tasks worker -l info -Q surveillance`.
- **`flower`** service (optional, demo-only) on port `5555` for Celery task UI — strong demo signal.

Add to `shared/`:
- **`shared/kafka_client.py`** — thin wrapper around `aiokafka` exposing `get_producer()`, `consume(topic, group_id, handler)`. Replaces `shared/redis_client.publish_event` for event publishing.
- **`shared/celery_app.py`** — Celery app factory: `celery_app = Celery("papertrail", broker=REDIS_URL, backend=REDIS_URL)`.

Migration steps per existing service: swap `publish_event(stream, ...)` → `await kafka_producer.send_and_wait(topic, payload)`; swap `XREADGROUP` consumers → `aiokafka.AIOKafkaConsumer` with `group_id`. Keep Redis for cache + Celery broker only.

### 5.1 Producer changes

- `services/edgar-ingester/src/ingester.py`:
  - After `filings` insert → produce to `filing.new` (Kafka).
  - After `insider_transactions` insert → produce to `insider.new` (Kafka).
- `services/transcript-ingester` → produce to `filing.new`.
- `services/claim-extractor` → produce to `claim.new`.
- `services/contradiction-detector` → produce to `contradiction.new`.

### 5.2 New service: `services/surveillance/`

```
services/surveillance/
  Dockerfile
  requirements.txt          # pandas, numpy, scipy, statsmodels, yfinance,
                            # asyncpg, aiokafka, redis, celery[redis], flower
  src/
    __init__.py
    main.py                 # Kafka consumer entrypoint
    consumer.py             # reads insider.new, enqueues Celery task
    tasks.py                # Celery: compute_event_study(transaction_id)
    event_study.py          # market-model regression + AR/CAR (pure)
    flagger.py              # threshold logic (pure)
    market_data.py          # yfinance fetch + Redis cache
    publisher.py            # produce to surveillance.flag, write flag row
    backfill.py             # one-shot replay of existing transactions
```

Runs as **two containers** in `docker-compose.yml`:
1. `surveillance` — Kafka consumer that enqueues Celery tasks.
2. `celery-worker` — runs the actual compute.

Splitting them means consumer lag and compute backpressure are observable separately, which is the whole point of using Celery.

### 5.3 Graph-builder additions

`services/graph-builder/src/consumer.py` extended to subscribe to two new Kafka topics:
- `insider.new` → `graph.upsert_insider_traded(...)` (writes `:Insider` node + `TRADED` edge).
- `surveillance.flag` → `graph.upsert_anomalous_movement(...)` (writes `ANOMALOUS_MOVEMENT` edge when `flagged=true`).

Two new methods on `Neo4jClient` in `graph.py` mirroring the Cypher in §4.4. Add `Insider` constraint in `setup_schema`.

### 5.4 API + dashboard

- `services/api-server/src/routers/surveillance.py` — `GET /surveillance/flags?limit=50` and `GET /surveillance/flags/{id}` (returns `daily_ar` for the drawer chart).
- WebSocket: api-server becomes a Kafka consumer (group `api-ws-fanout`) for `surveillance.flag` and `contradiction.new`, fans out to connected WS clients.
- Dashboard: `dashboard/src/components/SurveillancePanel.tsx` + drawer using existing chart lib.
- Dashboard: extend insider transaction timeline (per resume bullet) with anomaly overlay markers from flag data.

## 6. Event-study methodology (precise)

Let `t = 0` be `transaction_date` (next trading day if it falls on a weekend/holiday).

1. **Window:** baseline `T1 = [-30, -2]`, gap `[-1]` excluded, event `T2 = [0, +5]`. Trading days, not calendar days.
2. **Returns:** `r_i,t = (P_t - P_{t-1}) / P_{t-1}` for stock; `r_m,t` same for SPY.
3. **Market model fit on `T1`:** OLS `r_i = α + β · r_m + ε`. Save α, β, R².
4. **Expected return on `T2`:** `E[r_i,t] = α + β · r_m,t`.
5. **Abnormal return:** `AR_t = r_i,t - E[r_i,t]`.
6. **CAR:** `CAR = Σ AR_t` over `T2`.
7. **Standardization:** `z = CAR / (σ_AR_baseline · √N_event)` where `σ_AR_baseline` is std of residuals on `T1`, `N_event = 6`.
8. **Volume ratio:** `mean(Vol on T2) / mean(Vol on T1)`.
9. **Flag if:** `|z| > 2.0` AND `volume_ratio > 1.5`. (Both thresholds in env vars.)

### Edge cases
- **Insufficient price history** (e.g., recent IPO, < 25 baseline days): mark `flagged=false`, `flag_reason="insufficient_history"`, store nulls for stats.
- **Ticker not on yfinance** (delisted, foreign): same — record reason, don't crash.
- **Future event date** (T2 hasn't elapsed yet): defer — re-queue with delay; do not write a flag row.
- **Market holidays in window:** use actual trading days from SPY's index, not calendar arithmetic.

## 7. Configuration

New env vars (add to `shared/config.py`):

| Var | Default | Meaning |
|---|---|---|
| `SURV_BASELINE_DAYS` | 30 | Trading days before event |
| `SURV_EVENT_DAYS` | 5 | Trading days after event (window is `[0, +N]`) |
| `SURV_CAR_Z_THRESHOLD` | 2.0 | |z| flag threshold |
| `SURV_VOLUME_THRESHOLD` | 1.5 | volume ratio flag threshold |
| `SURV_MARKET_INDEX` | SPY | benchmark ticker |
| `SURV_PRICE_CACHE_TTL` | 86400 | seconds |
| `SURV_DEFER_IF_INCOMPLETE` | true | re-queue if event window not yet elapsed |

## 8. Dependencies

**`services/surveillance/requirements.txt`:**
```
pandas>=2.2
numpy>=1.26
scipy>=1.13
statsmodels>=0.14
yfinance>=0.2.40
asyncpg>=0.29
aiokafka>=0.11
redis>=5.0
celery[redis]>=5.4
flower>=2.0
pydantic>=2.0
```

**Add to every service's requirements.txt** (replacing direct redis-stream usage):
```
aiokafka>=0.11
```

**New compose services:**
- `redpandadata/redpanda:latest` (Kafka API on `:9092`, admin on `:9644`)
- `celery-worker` (built from `services/surveillance/`)
- `flower` (optional, demo)

## 9. Testing

- **Unit:** `event_study.py` against a synthetic series with known α=0, β=1, injected +5% AR on day 0 → CAR ≈ 0.05, z high.
- **Unit:** flagger thresholds (boundary cases).
- **Integration:** mock yfinance, publish a fake `insider.new` event, assert row in `surveillance_flags` and message on `surveillance.flag`.
- **Manual smoke:** pick a known historical insider buy with a public stir (e.g., a CEO open-market purchase preceding a pop) — verify the system flags it.

## 10. Risks & open questions

| Risk | Mitigation |
|---|---|
| yfinance rate limits / silent failures | Cache per (ticker, date_range) in Redis; retry w/ backoff; surface as `flag_reason` |
| Look-ahead bias if event window not complete | Defer logic in §6 edge cases |
| `transaction_date` ≠ `filing_date` — which to use as t=0? | Use **transaction_date** (when the insider actually traded); document this |
| Many transactions per filing → duplicate yfinance calls | Batch by (ticker, date) and dedupe in `market_data.py` |
| Survivorship/delisting | Flag with reason, don't crash |

## 11. Milestones

**Phase A — Event-bus migration (foundation, no user-visible change):**
1. **M0a — Redpanda + kafka_client**: add Redpanda to compose; create `shared/kafka_client.py`; smoke-test produce/consume from a one-off script.
2. **M0b — Migrate existing producers/consumers**: edgar-ingester, transcript-ingester, claim-extractor, contradiction-detector, graph-builder, api-server WS. Keep redis_client.py around but stop calling `publish_event`. Verify end-to-end pipeline still works on a single test filing.
3. **M0c — Celery scaffold**: `shared/celery_app.py`, dummy task, celery-worker container, Flower. Verify `task.delay()` round-trips.

**Phase B — Surveillance feature:**
4. **M1 — Schema**: `surveillance_flags` table; `Insider` constraint in Neo4j `setup_schema`.
5. **M2 — Pure logic**: `event_study.py` + `flagger.py` + unit tests with synthetic data.
6. **M3 — Wiring**: `market_data.py` (yfinance + Redis cache), `tasks.py` (Celery task), `consumer.py` (Kafka → enqueue), `publisher.py` (Kafka producer for `surveillance.flag`).
7. **M4 — Graph edges**: `Neo4jClient.upsert_insider_traded` + `upsert_anomalous_movement`; subscribe graph-builder to `insider.new` and `surveillance.flag`.
8. **M5 — API + dashboard**: `/surveillance/flags` routes, `SurveillancePanel.tsx`, drawer chart, anomaly overlay on existing insider timeline.
9. **M6 — Backfill + polish**: `backfill.py` script to replay existing `insider_transactions`; threshold tuning; README updates.

**Estimated total:** ~700–1000 LoC Python + ~200 LoC TS. Phase A is ~1.5 days of mostly mechanical migration; Phase B is the original ~weekend estimate. Total realistic budget: **4–5 focused days**.
