# PaperTrail — next steps when you pick this back up

Last updated 2026-05-21. This is the "open me first" doc. Everything here is either (a) something you have to run by hand because Claude can't, or (b) a deferred refactor with a concrete starting point.

Full context lives in `CLAUDE.md`. Background on individual chunks: `docs/security-audit.md`, `docs/surveillance-plan.md`, `docs/surveillance-prd.md`.

---

## 0. What's already done (just so you know what state you're in)

- ✅ Surveillance backfill script (`services/surveillance/src/backfill.py`)
- ✅ README rewrite (Kafka topics, surveillance module, Flower, backfill, threshold tuning sections)
- ✅ Dead Redis code removed; stale docs in `docs/docker-dashboard-notes.md` fixed
- ✅ Security audit (`docs/security-audit.md`)
- ✅ Phase 1+2 security hardening (CORS, security headers, input validation, prompt isolation, loopback-only infra ports, .env warning)

Branch state: `main` is clean. None of the above has been committed yet — check `git status` first.

---

## 1. Verify the security patches on a running stack (10 min)

Do this first. If anything below fails, fix before merging the security work.

```bash
docker compose up -d --build api-server dashboard
```

**Headers test** — should show `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: strict-origin-when-cross-origin`:
```bash
curl -i http://localhost:8000/health
```

**Dashboard still loads** — open http://localhost:3000, confirm the contradictions feed + surveillance panel render without CORS errors in the browser console.

**CORS rejects unknown origins** — should NOT echo `access-control-allow-origin: https://evil.com`:
```bash
curl -i -H "Origin: https://evil.com" http://localhost:8000/api/v1/stats | grep -i access-control
```

**Loopback binding works** — should be **refused** from another machine on your LAN (or set `IP=$(ipconfig getifaddr en0)` on Mac):
```bash
nc -zv $(ipconfig getifaddr en0) 5432   # postgres — should fail
nc -zv $(ipconfig getifaddr en0) 7474   # neo4j   — should fail
nc -zv $(ipconfig getifaddr en0) 8000   # api     — should succeed
```

**Email validation works** — should return 422:
```bash
curl -i -X POST http://localhost:8000/api/v1/watchlist \
  -H 'Content-Type: application/json' \
  -d '{"email":"not-an-email","ticker":"AAPL"}'
```

**Search query cap works** — should return 422:
```bash
curl -i "http://localhost:8000/api/v1/search/claims?q=$(python3 -c 'print(\"a\"*250)')"
```

If all five pass: `git add -A && git commit -m "Security hardening (Phases 1+2)"`.

---

## 2. M6 — finish the surveillance milestone (you-side)

### 2a. Run the backfill + tune thresholds

Goal: target a 5–15% flag rate.

```bash
# preview
docker compose run --rm --no-deps surveillance \
    python -m surveillance.backfill --dry-run

# enqueue
docker compose run --rm --no-deps surveillance \
    python -m surveillance.backfill --limit 200

# watch
open http://localhost:5555    # Flower
docker compose logs -f celery-worker
```

When tasks finish, check the rate:
```bash
docker compose exec postgres psql -U papertrail -d papertrail -c "
SELECT COUNT(*) FILTER (WHERE flagged) * 1.0 / NULLIF(COUNT(*),0) AS flag_rate,
       COUNT(*) FILTER (WHERE flagged) AS flagged,
       COUNT(*) AS total
FROM surveillance_flags;"
```

If outside 5–15%, edit `.env` (`SURV_CAR_Z_THRESHOLD=2.0`, `SURV_VOLUME_THRESHOLD=1.5`), restart `celery-worker`, and re-run with `--overwrite`. Record the final chosen thresholds + observed rate in `docs/surveillance-plan.md` under "Decision log".

### 2b. Eyeball the dashboard

Open http://localhost:3000 with the stack up. Confirm:
- SurveillancePanel renders between Charts and Contradictions Feed without layout breakage.
- Click a flagged row → drawer opens → 3-line recharts plot (AR, realized, expected) renders → α/β/R² visible.

Fix any CSS / spacing issues inline.

### 2c. Capture screenshots for the README

- `docs/img/flower.png` — Flower with at least one SUCCESS task.
- `docs/img/surveillance-panel.png` — dashboard panel + open drawer.

Embed both in `README.md` under "Surveillance module".

### 2d. Verify Form 4 ingestion against a real CIK

The hardcoded `xslF345X05/` path was already replaced with `primaryDocument` from EDGAR submissions JSON, but no real-CIK end-to-end run is documented yet. Run it once with a real S&P 500 CIK and confirm:

```bash
docker compose exec edgar-ingester python -c \
  "import asyncio; from src.form4_parser import run_form4_ingestion; asyncio.run(run_form4_ingestion())"

# check rows landed
docker compose exec postgres psql -U papertrail -d papertrail -c \
  "SELECT COUNT(*), MAX(transaction_date) FROM insider_transactions;"

# check insider.new fired and surveillance picked it up
docker compose exec redpanda rpk topic consume insider.new --num 5
docker compose logs --tail 100 surveillance celery-worker | grep -i flagged
```

If transactions land and `surveillance.flag` events follow → close the "pre-existing Form 4" item in `CLAUDE.md` §15.

---

## 3. Deferred security work (separate PRs, in priority order)

Pick these up after M6 closes. Each is its own PR.

### 3a. Rate limiting (`slowapi`) — ~30 min

Why: search endpoint loads a 90 MB model and runs an embedding per request; no cap today. WebSocket connection count unbounded.

```python
# services/api-server/requirements.txt — add
slowapi>=0.1.9
```

```python
# services/api-server/src/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Then in `routers/search.py` decorate `/search/claims` with `@limiter.limit("10/minute")`, and in `routers/ws.py` cap `len(manager.active_connections)` at 200 — reject new accepts beyond that with `await websocket.close(code=1013)`.

Verify:
```bash
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code} " "http://localhost:8000/api/v1/search/claims?q=test"
done
# expect a mix of 200 and 429
```

### 3b. Contradiction-detector → Celery for Ollama enrichment — ~50 LoC

Why: `services/contradiction-detector/src/agent.py:evaluate_contradiction_pair` awaits `generate_reasoning(...)` (60s timeout) inside the single Kafka consumer. One slow LLM call stalls the whole `claims.extracted` topic. Same anti-pattern surveillance solved with Celery.

Shape:

1. New task module `services/contradiction-detector/src/tasks.py`:
   ```python
   @celery_app.task(name="contradiction.enrich_reasoning", bind=True, max_retries=3)
   def enrich_contradiction_reasoning(self, contradiction_id: int) -> dict: ...
   ```
   Body: fetch row + claim context via sync psycopg2, call `generate_reasoning` (will need a sync wrapper — easiest: `asyncio.run(...)` since Celery prefork is sync), `UPDATE contradictions SET agent_reasoning = ... WHERE id = ...`, return.

2. In `agent.py`: stop awaiting `generate_reasoning`. Set `agent_reasoning=None` in the returned dict.

3. In `detector.py:detect_contradictions_for_filing`, after `insert_contradiction(...)` returns `contra_id`, call `enrich_contradiction_reasoning.delay(contra_id)`.

4. Add `services/contradiction-detector/src/tasks.py` to `shared/celery_app.py` `include=[...]`.

5. Add `celery[redis]>=5.4` to `services/contradiction-detector/requirements.txt` if not present.

6. Optional: publish `contradiction.updated` from the task so the dashboard can live-refresh.

Verify: `docker compose logs -f contradiction-detector` should never block for >1s; `celery-worker` logs should show `contradiction.enrich_reasoning` tasks STARTED → SUCCESS.

### 3c. Dependency pinning + CI audit — half a day

Per service:
```bash
docker compose run --rm --no-deps <service> sh -c \
  "pip install pip-tools && pip-compile requirements.txt -o requirements.lock"
```

Commit the lockfiles. Update each Dockerfile to `pip install -r requirements.lock`. Add `.github/workflows/audit.yml` running `pip-audit` + `npm audit --omit=dev` on PRs.

### 3d. Auth — only when going multi-tenant

If PaperTrail ever ships beyond a personal laptop, **this is the hard blocker** — everything else on the security checklist depends on it. Current watchlist endpoints key on a plain `email` query param. See `docs/security-audit.md` §1 + §2.

Likely choice: `fastapi-users` + Postgres backend, or Clerk if you don't want to run an auth service.

---

## 4. Optional / nice-to-haves

- **`InsiderTimeline.tsx`** — the deferred M5 component. Only worth it once you have many flagged events to compare across. Drawer already covers single-event view.
- **Live scans:**
  - `gitleaks detect --source .` before making the repo public
  - OWASP ZAP against `http://localhost:8000` with the stack up
  - `k6` load test on `/api/v1/search/claims` after 3a ships to verify rate limit

---

## 5. Cheat-sheet — most common commands

```bash
# Full stack
docker compose up --build

# Just rebuild one service after a code change
docker compose up -d --build api-server

# Tail logs (the three most useful)
docker compose logs -f contradiction-detector   # [AGENT] / [AGENT_TOOL] lines
docker compose logs -f celery-worker            # surveillance event-study
docker compose logs -f graph-builder            # Neo4j upserts

# Postgres shell
docker compose exec postgres psql -U papertrail -d papertrail

# Kafka topic peek
docker compose exec redpanda rpk topic list
docker compose exec redpanda rpk topic consume surveillance.flag --num 5

# Surveillance unit tests
docker compose run --rm --no-deps celery-worker pytest surveillance/tests -q

# Ollama model pull (after changing OLLAMA_MODEL)
docker compose exec ollama ollama pull tinyllama
```
