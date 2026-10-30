# PaperTrail Lite: plan to fix, slim down, and ship live

**Status:** Draft v1, written 2026-10-29. Nothing in this plan has been implemented yet.

> **Update 2026-10-30:** the recommended first deployment is now a static snapshot on Vercel (option A in `docs/deployment-options.md`). This document's Neon + GitHub Actions setup is option C, for when you want nightly automatic updates. The fixes and tool-calling work now has its own detailed plan: `docs/fixes-and-tool-calling-plan.md`.
**Companion docs:** `docs/worklog.md` (dated log of what actually happened), `CLAUDE.md` (project context), `docs/next-steps.md` (older M6 checklist; still valid for the Docker stack).

---

## 0. Goals and non-goals

### Goals
1. **A public, live URL** that shows real (not mock) PaperTrail output for a fixed set of S&P 500 companies, refreshed on a schedule.
2. **Near-zero running cost**: free tiers only, plus an LLM API key with a hard monthly spend cap.
3. **No Docker needed for the live version.** The live system is one Next.js app, one Postgres database, and one scheduled Python job.
4. **Fix the correctness bugs** found in the 2026-10-29 review before any of it goes public.
5. **Real tool calling**: an LLM that chooses which tools to call, not a fixed sequence of Python functions.
6. **A measured accuracy number** (precision of flagged contradictions) so the project's claims can be defended.

### Non-goals (for now)
- Real-time processing. A nightly batch is fine; SEC filings don't arrive by the second.
- All 500 companies. Start with ~25.
- Auth and multi-tenant watchlists. The watchlist feature is hidden in the live version.
- Neo4j in production. The graph stays in the local Docker mode.

### What stays
The Docker Compose stack (Kafka/Redpanda, Celery, Neo4j, Ollama, 14 containers) stays in the repo as **"full mode"**: the event-driven reference architecture you can run locally and talk about in interviews. **"Lite mode"** is what's deployed. Both modes run the **same core NLP and finance code**, so improvements land in both.

---

## 1. Why the current stack can't go live as-is

| Component | Problem for hosting |
|---|---|
| 14 always-on containers | Needs a VM with ~8–16 GB RAM running 24/7. No free tier covers that. |
| Ollama + tinyllama | Needs its own RAM. Its summaries are also weak. |
| Neo4j | A separate stateful service. The dashboard doesn't depend on it. |
| Redpanda + Celery + Redis | Only needed for streaming. A nightly batch doesn't need a message bus. |
| FinBERT + MiniLM + DeBERTa NLI | ~1.5 GB of models on CPU. Fine in a batch job, too heavy for a serverless web request. |
| WebSocket `/ws/feed` | Vercel serverless functions don't keep WebSocket connections open. |
| `filings.raw_text` | Full 10-K text is hundreds of KB per filing. That blows through a 1 GB free database fast. |

The key point: **the heavy work only has to happen when new filings arrive.** Run it once a night on a free CI runner, write the results to Postgres, and the website only reads from the database.

---

## 2. Target architecture (lite mode)

```
┌──────────────────────────── GitHub Actions (nightly cron) ────────────────────────────┐
│  ubuntu-latest, public repo → 4 CPU / 16 GB RAM, free                                 │
│                                                                                        │
│  python -m papertrail.run --config config/tickers.yml                                  │
│    1. ingest     EDGAR submissions JSON → new 10-K / 10-Q / 8-K since last accession    │
│    2. extract    sectionize → sentences → claim filter → FinBERT → MiniLM (384-d)       │
│    3. detect     pgvector neighbours → batched NLI → rules severity                     │
│    4. verify     LLM checker agent (tool calling) on NLI-positive pairs only            │
│    5. form4      Form 4 XML → insider_transactions                                      │
│    6. surveil    prices (cached in Postgres) → market model → CAR / z / vol ratio       │
│    7. record     pipeline_runs row: counts, durations, errors                           │
│  HF model cache via actions/cache, so models aren't re-downloaded on every run         │
└───────────────────────────────────────┬────────────────────────────────────────────────┘
                                        │ DATABASE_URL (GitHub secret)
                                        ▼
                         ┌───────────────────────────────┐
                         │  Neon Postgres (free plan)     │
                         │  pgvector, ~1 GB per project   │
                         └───────────────┬───────────────┘
                                         │ read-only role (Vercel env var)
                                         ▼
┌──────────────────────────── Vercel (Next.js 14, Hobby) ───────────────────────────────┐
│  Server components / route handlers query Neon directly (@neondatabase/serverless)    │
│  /                dashboard (stats, severity chart, contradictions, surveillance)      │
│  /company/[t]     timeline, claims, contradictions, insiders                           │
│  /ask             "Ask PaperTrail": Claude tool-use loop over SQL-backed tools         │
│  /status          last pipeline runs (from pipeline_runs)                              │
│  Live feed → "new since last run" list with SWR polling (no WebSocket)                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Why these three services
- **Neon free plan** (checked 2026-10-29 on neon.com/pricing): 1 GB storage per project, 100 compute-unit-hours per project per month, suspends after 5 minutes idle, pgvector included, no credit card. A nightly job plus light website traffic fits easily. The one real limit is the 1 GB, so §6 has a storage budget.
- **GitHub Actions** (checked 2026-10-29 on docs.github.com): standard runners are free and unlimited for public repos, and public-repo `ubuntu-latest` gets 4 CPU / 16 GB RAM. That's enough for the three transformer models on CPU. **The repo must stay public**; private repos get 2 CPU / 8 GB and limited minutes.
- **Vercel Hobby**: `vercel.json` already exists. Hobby is for non-commercial use, which covers a portfolio project. Check the function timeout limits on Hobby before building `/ask`; the plan streams responses and caps tool rounds so each request stays short.

### Alternatives considered
| Option | Why not (for now) |
|---|---|
| Keep FastAPI and host it on Render/Fly/Railway | One more service to keep awake, and free tiers sleep (slow first request). Next.js can query Postgres directly. FastAPI stays for full mode. |
| Supabase instead of Neon | Also fine (pgvector, free tier). Neon picked for scale-to-zero and branching (handy for preview databases). Either works; decision D2. |
| Modal / HF Spaces for the pipeline | Good later if runs get slow. GitHub Actions is free and lives next to the code. |
| Hosted embedding API instead of MiniLM | Changes the embeddings and adds cost. MiniLM on a CI runner is free. |

---

## 3. Phases at a glance

| Phase | What | Rough effort | Depends on |
|---|---|---|---|
| **P0** | Branch, worklog, baseline snapshot | 1 h | — |
| **P1** | Correctness fixes + runnable tests + CI | 4–6 h | P0 |
| **P2** | Evaluation set + baseline precision | 4–8 h (mostly labeling) | P1 |
| **P3** | Extract core package; lite pipeline runner | 8–12 h | P1 |
| **P4** | Neon + GitHub Actions + Vercel deploy | 5–8 h | P3 |
| **P5a** | LLM checker agent (tool calling, in the pipeline) | 6–10 h | P2, P3 |
| **P5b** | "Ask PaperTrail" chat (tool calling, on the website) | 6–10 h | P4 |
| **P6** | Polish: README, diagrams, screenshots, guardrails, status page | 3–5 h | P4, P5 |

Total ≈ 40–60 focused hours. P1 → P3 → P4 is the shortest path to a live URL. P2 and P5a can run alongside P4.

---

## 4. Phase P0: set up (≈1 h)

- [ ] Create branch `lite/p1-fixes` from `main` (one branch per phase, merged via PR).
- [ ] Create `docs/worklog.md` (done 2026-10-29) and add a dated entry every working session.
- [ ] Add a pointer to this plan in `CLAUDE.md` (done 2026-10-29).
- [ ] If the Docker stack still runs locally, snapshot current row counts (`companies`, `filings`, `claims`, `contradictions`, `insider_transactions`, `surveillance_flags`) into the worklog as a baseline.
- [ ] Clean up git housekeeping: `.DS_Store` files are already ignored, but add `**/.DS_Store` to `.gitignore` for subfolders. Move `Papertrail.pdf` (1.7 MB) to `docs/` or a release asset.

**Done when:** branch exists, worklog has its first entry.

---

## 5. Phase P1: correctness fixes (≈4–6 h)

### P1.1 Duplicate contradictions (bug)
**Problem:** `contradictions` has no unique key, and `insert_contradiction` (`shared/db.py`) has no `ON CONFLICT`. With at-least-once Kafka delivery or out-of-order backfills, the same claim pair is stored more than once. The README says handlers are idempotent, which isn't true for this table.

**Fix:**
1. Migration `infra/migrations/001_contradiction_unique.sql`:
   ```sql
   -- remove existing duplicates, keep the earliest row per unordered pair
   DELETE FROM contradictions c
   USING contradictions d
   WHERE c.id > d.id
     AND LEAST(c.claim_a_id, c.claim_b_id)    = LEAST(d.claim_a_id, d.claim_b_id)
     AND GREATEST(c.claim_a_id, c.claim_b_id) = GREATEST(d.claim_a_id, d.claim_b_id);

   CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_pair
     ON contradictions (LEAST(claim_a_id, claim_b_id), GREATEST(claim_a_id, claim_b_id));
   ```
2. `insert_contradiction` → `ON CONFLICT ((LEAST(claim_a_id, claim_b_id)), (GREATEST(claim_a_id, claim_b_id))) DO NOTHING RETURNING id`. Return `None` on conflict.
3. `detector.py`: if `insert_contradiction` returns `None`, **don't** publish `contradiction.found` (otherwise the dashboard gets duplicate live events).
4. Optimization: before running the NLI and Ollama steps, check whether the pair already exists, so the expensive work isn't redone on redelivery.
5. Mirror the index into `infra/init.sql` for fresh installs.

**Test:** unit test that inserts the same pair twice, in both orders (a,b) and (b,a), and gets one row.

### P1.2 Duplicate insider transactions (bug)
**Problem:** `insider_transactions` has no unique constraint, so `ON CONFLICT DO NOTHING` in `form4_parser.py` never fires. Re-running Form 4 ingestion duplicates trades. That (a) enqueues duplicate surveillance tasks and (b) inflates `total_sell_value` / `sell_count` in `summarize_insider_rows`, which can **wrongly raise contradiction severity**.

**Fix:**
1. Add `accession_number VARCHAR(25)` and `line_no INT` to `insider_transactions` (populated by the Form 4 parser from the filing accession and the transaction's position in the XML).
2. `UNIQUE (accession_number, line_no)`. For legacy rows without an accession number, dedupe on `(company_id, insider_name, transaction_date, transaction_type, shares, price)` in the migration, then backfill or drop them.
3. Change the insert to `ON CONFLICT (accession_number, line_no) DO NOTHING`. The existing `continue` on conflict then works as intended.

**Test:** parse the same Form 4 fixture twice and get one set of rows and one `insider.new` publish per transaction.

### P1.3 Make all tests runnable
**Problems:**
- `tests/test_severity_scorer.py` does `sys.path.insert(0, "/Users/ketaki.dabade/papertrail")`, so it only works on one laptop.
- `models/severity-scorer/` and `services/transcript-ingester/` have hyphens in their names, so they can't be imported as Python packages.
- Surveillance tests import `surveillance.event_study`, which only resolves inside the Docker image.

**Fix (short term, before P3):**
- Add `conftest.py` at the repo root that puts the right folders on `sys.path`, or symlinks/aliases the hyphenated folders.
- Remove the hardcoded `/Users/...` path.
- Add `pytest.ini` with `testpaths = tests services/surveillance/tests`.

**Fix (long term, in P3):** the core package (`papertrail/`) has normal import names, and the tests import from it.

**Done when:** `pytest -q` from the repo root collects and passes all 4 test files (11+ tests) with no Docker.

### P1.4 CI
`.github/workflows/ci.yml`, on every push and PR:
- Python 3.11: install lightweight deps (no torch), run `pytest -q -m "not models"`. Tests that need model weights get a `@pytest.mark.models` marker and run only in the nightly job.
- Node 20: `cd dashboard && npm ci && npm run lint && npm run build`.
- Optional: `pip-audit` and `npm audit --audit-level=high` as non-blocking steps (from the security-audit deferred list).

### P1.5 Faster, non-blocking NLI
**Problem:** `agent.py` calls `check_negation` one pair at a time, and the model runs synchronously inside the async event loop, blocking it.

**Fix:** in `detector.py`, collect all candidates for a filing, call `score_pairs` once on the whole batch (it already accepts a list), and run it with `await asyncio.to_thread(...)`. Then only NLI-positive pairs go through the rest of the agent steps. Same treatment for FinBERT and MiniLM in the claim extractor if they block.

**Measure:** time per filing before/after, logged in the worklog.

### P1.6 Smaller fixes
- [ ] README: correct the "handlers are idempotent" sentence once P1.1–P1.2 make it true.
- [ ] Dashboard mock mode: `SurveillancePanel` calls `/api/v1/surveillance/flags`, which has no mock route, so the panel is empty in demo mode. Add a mock route, or hide the panel when there's no API. (Lite mode replaces mocks with real data anyway.)
- [ ] `get_similar_claims` computes the cosine distance twice (`WHERE` and `ORDER BY`). Fine at this scale; note it for later.

**P1 done when:** both bugs fixed with migrations and tests, `pytest` and the dashboard build pass in CI, worklog updated.

---

## 6. Phase P2: evaluation set (≈4–8 h, mostly labeling)

Without this, nobody can tell whether the system works. It's also what makes the P5a agent defensible.

1. **Sample** ~200 pairs the current pipeline flagged (NLI ≥ 0.6), spread across severities and topics. Add ~50 pairs that were *just below* the threshold to estimate what's being missed.
2. **Label** each pair in a simple CSV (`eval/pairs.csv`): `pair_id, claim_a, claim_b, ticker, dates, label, notes`, with label one of:
   - `real`: a genuine change in stance or facts that an analyst would care about
   - `update`: a new number replacing an old one (e.g. guidance revised); not a contradiction but worth tracking
   - `boilerplate`: hedged risk-factor language ("may", "could") against an actual event
   - `scope`: different products, segments or periods
   - `noise`: bad sentence split, table fragment, etc.
3. **Script** `eval/run_eval.py`: precision overall and by severity, confusion matrix against labels, and a list of the worst false positives.
4. **Record the baseline** in this doc and in the worklog (e.g. "rules-only precision = X% at NLI ≥ 0.6").
5. Run it again after every change that matters (P1.5, claim-filter changes, P5a). The eval set is frozen; never tune on the test split. Use a 50/150 dev/test split.

**Tip:** label in a spreadsheet, export to CSV. Two or three hours of focused labeling gets you there.

---

## 7. Phase P3: core package + lite pipeline (≈8–12 h)

### P3.1 Extract a core package
Today the logic lives in `services/*/src/` and depends on Docker paths (`sys.path.insert(0, "/app")`, `from shared...`). Move the **pure logic** into one installable package:

```
papertrail/                      # new, pip install -e .
  pyproject.toml
  papertrail/
    config.py                    # from shared/config.py
    db.py                        # from shared/db.py (asyncpg), plus migrations runner
    edgar/   client.py, form4.py, sp500.py
    nlp/     splitter.py, claims.py (FinBERT), embed.py (MiniLM), entities.py, topics.py
    detect/  nli.py, tools.py (from agent_tools.py), severity.py, pipeline.py
    agent/   checker.py, tools.py, prompts.py          # P5a
    surveil/ event_study.py, flagger.py, prices.py
    run.py                       # lite-mode CLI (below)
```

The Docker services then become thin wrappers: their Kafka handlers call into `papertrail.*`. Each Dockerfile does `pip install /papertrail` instead of copying `shared/` and `src/`. This keeps full mode working with one copy of the code. (Decision D1: if keeping Docker mode working feels like too much, freeze it at the current commit and tag it `v1-full-architecture`.)

### P3.2 Lite runner
`python -m papertrail.run --config config/tickers.yml [--stages ingest,extract,detect,verify,form4,surveil] [--since 2024-01-01] [--dry-run]`

- **Stages are resumable.** Add `filings.stage` (`ingested → extracted → detected → verified`). Each stage only picks up rows at the previous stage, so a crashed run continues where it stopped the next night.
- **Incremental.** Ingest only accessions newer than what's stored per company.
- **Bounded.** `--max-filings` per run and per company, so one huge backlog can't blow the job time.
- **Logged.** One `pipeline_runs` row per run: started_at, finished_at, git SHA, per-stage counts, errors (JSON). The dashboard's `/status` page reads this.
- **Same stages as full mode.** Only the transport differs (a for-loop instead of Kafka topics).

### P3.3 Storage budget (to fit Neon's 1 GB)
Estimates below are rough; **measure them on 3 tickers first** and record the real numbers in the worklog.

| Item | Change | Why |
|---|---|---|
| `filings.raw_text` | **Don't store in lite mode.** Keep `url`; re-download if needed. | Biggest table by far (10-Ks are hundreds of KB each). |
| Claim context | New `claims.context_text`: previous + next sentence (~500 chars). | The checker agent and UI need context, not the whole filing. |
| Embeddings | `vector(384)` → `halfvec(384)` (pgvector ≥ 0.7) | Halves embedding storage, with negligible quality loss for similarity search. |
| Claim volume | Restrict to 10-K/10-Q *Risk Factors* + *MD&A*, plus 8-K EX-99.1; tighten the claim filter; dedupe identical sentences across filings (boilerplate repeats every quarter). | Repeated boilerplate is both the storage problem and the false-positive problem. |
| Scope | ~25 tickers × last 2 years. | Expand once the real per-ticker size is known. |
| Prices | New `prices(ticker, date, close, volume)` table; fetch only missing days. | Replaces the Redis cache, and avoids re-hitting Yahoo every night. |

Add `scripts/db_size.sql` (table sizes via `pg_total_relation_size`) and log the output after each run.

### P3.4 Ticker set
`config/tickers.yml`: ~25 large caps across ~5 sectors (tech, banks, energy, pharma, consumer), including a few companies with known guidance changes or restructurings so the demo has something interesting to show. Each entry: `ticker, cik, sector`.

**P3 done when:** `python -m papertrail.run` on a laptop against a local Postgres (Homebrew/Postgres.app with pgvector; no Docker) processes 3 tickers end to end, and `eval/run_eval.py` still produces the same precision as P2.

---

## 8. Phase P4: go live (≈5–8 h)

### P4.1 Neon
- [ ] Create project `papertrail` (region close to where the GitHub runners and Vercel functions run, e.g. US East).
- [ ] Enable `vector`; run `infra/init.sql` + migrations via `python -m papertrail.db migrate`.
- [ ] Two roles: `pipeline_rw` (GitHub Actions) and `web_ro` (Vercel, `SELECT` only, plus `INSERT` on the `/ask` rate-limit table).
- [ ] Use a Neon branch for testing migrations before applying them to `main`.

### P4.2 Nightly GitHub Actions job
`.github/workflows/pipeline.yml`:
- `on: schedule` (once a night, e.g. 06:00 UTC, after EDGAR's evening filings) + `workflow_dispatch` for manual runs.
- `concurrency: pipeline` so two runs never overlap.
- Steps: checkout → set up Python 3.11 → `actions/cache` for `~/.cache/huggingface` and pip → `pip install -e ./papertrail` with CPU-only torch → `python -m papertrail.run` → upload logs as an artifact.
- Secrets: `DATABASE_URL`, `EDGAR_USER_AGENT` (real name + email, as SEC requires), `ANTHROPIC_API_KEY` (P5a).
- `timeout-minutes: 120` as a safety net.
- On failure: GitHub emails you by default; the `pipeline_runs` row also records the error.

**First backfill:** run the 2-year backfill manually via `workflow_dispatch` with `--max-filings` in chunks, watching DB size after each.

### P4.3 Dashboard on Vercel
- [ ] Add `dashboard/src/lib/db.ts` using `@neondatabase/serverless` (HTTP driver works well in serverless functions).
- [ ] Port the read endpoints the UI uses from FastAPI to Next.js route handlers or server components: `stats`, `contradictions/latest`, `companies`, `companies/[t]` (+ timeline, claims, contradictions, insiders), `surveillance/flags` (+ detail). The SQL already exists in `services/api-server/src/routers/*.py`, so this is mostly translation.
- [ ] **Search:** the current semantic search embeds the query with SentenceTransformers in Python, which a Vercel function can't easily do. Phase 1: Postgres full-text search (`tsvector` column + GIN index on `claim_text`) with `pg_trgm` as fallback. Phase 2 (optional): run MiniLM in the function via `@huggingface/transformers` (ONNX) and keep pgvector search. Decision D4.
- [ ] **Live feed:** replace the WebSocket with "new since last run" (contradictions with `created_at > last run`) and SWR polling every 60 s.
- [ ] Hide the watchlist in lite mode (no auth).
- [ ] Keep the mock data as a fallback only when `DATABASE_URL` is missing (local UI dev).
- [ ] Vercel project: root directory `dashboard`, env `DATABASE_URL` (web_ro), connect the GitHub repo so `main` deploys automatically and PRs get preview URLs.
- [ ] Add `/status`: last 14 pipeline runs, counts, durations, errors.

### P4.4 Abuse protection (public site)
- Read pages: cache server-rendered data (`revalidate` ~10 minutes); data only changes nightly.
- `/ask` (P5b): rate limit per IP stored in a Postgres table (no extra service), max tokens per answer, max tool rounds, and a global daily request cap. Plus a hard monthly spend limit in the Anthropic Console.

**P4 done when:** a public `*.vercel.app` URL shows real contradictions and surveillance flags for the ticker set, the nightly job has run successfully 3 nights in a row, and `/status` shows it.

---

## 9. Phase P5: real tool calling

### What's wrong with the current "agent"
`agent.py` always calls the same five functions in the same order; the LLM only writes a paragraph at the end from a digest it's given. That's a pipeline with logging, not an agent. In an agent, **the model decides which tools to call, with what arguments, and when it has enough evidence**, and its decision changes the outcome.

### P5a: Contradiction checker agent (runs in the nightly pipeline)

**Job:** for each pair that passes NLI, decide whether it's a real contradiction, investigate as needed, and return a structured verdict. This directly targets the false positives measured in P2.

**Model:** Claude via the Anthropic API with tool use (Haiku-class by default for cost; configurable via `CHECKER_MODEL`). Ollama stays as an option for full mode.

**Tools** (Python functions in `papertrail/agent/tools.py`, all read-only, all scoped to the pair's company):

| Tool | Args | Returns |
|---|---|---|
| `get_claim_context` | `claim_id` | sentence + `context_text`, section, filing form/date, URL |
| `find_related_claims` | `topic?`, `query?`, `date_from?`, `date_to?`, `limit≤10` | other claims from the same company (pgvector or full-text) |
| `run_nli` | `text_a`, `text_b` | contradiction / entailment / neutral probabilities |
| `get_insider_trades` | `date_from`, `date_to` | Form 4 rows + summary (sells, notional) |
| `get_event_study` | `transaction_id` | CAR, z, vol ratio, flagged |
| `get_price_move` | `date_from`, `date_to` | stock vs SPY return over the window |
| `submit_verdict` | see schema | ends the loop |

**Verdict schema** (`submit_verdict`, enforced as the final tool):
```json
{
  "verdict": "real | update | boilerplate | scope | noise",
  "severity": "low | medium | high | critical",
  "confidence": 0.0,
  "rationale": "2–4 sentences, cites claim ids",
  "evidence": [{"tool": "get_insider_trades", "why": "..."}]
}
```
The labels match the P2 eval labels, so the agent can be scored directly.

**Loop and guardrails:**
- At most 6 tool calls per pair; then it must call `submit_verdict`.
- Daily cap on pairs checked (e.g. 200) and on total tokens; stop cleanly when hit and resume tomorrow.
- Cache by pair id: never re-check a pair unless the prompt version changes.
- Reuse the existing prompt-injection protection (`_neutralize_tags`, data in tagged blocks), since filing text is untrusted.
- Store every run in a new `agent_runs` table: pair id, model, prompt version, each tool call with args and a truncated result, verdict, tokens, latency. This is the "visible tool trace".

**What changes downstream:**
- `contradictions` gets `verdict`, `agent_confidence`, `agent_run_id`.
- The dashboard shows `real` (and optionally `update`) by default, with a toggle to show everything, and each card gets a "How was this checked?" expander that renders the tool trace.

**Evaluation (the point of P2):** run the checker on the P2 test split and report precision of (rules only) vs (rules + checker), plus cost per 100 pairs. Write the numbers here and in the README.

### P5b: "Ask PaperTrail" (runs on the website)

**Job:** an analyst types a question ("Did Boeing's language on 737 production change before insiders sold?"); Claude calls tools against the database and answers with citations to claims and filings. Tool calls stream to the UI as they happen.

**Where:** a Next.js route handler (`/api/ask`) using the Anthropic TypeScript SDK with streaming. Tools are SQL-backed only (no NLI on Vercel):
`list_companies`, `search_claims` (full-text; semantic if D4 done), `get_contradictions(ticker, severity?, verdict?)`, `get_timeline(ticker, from, to)`, `get_insider_trades(ticker, from, to)`, `get_surveillance_flags(ticker)`.

**Rules:** answers must cite claim/filing ids (rendered as links to `/company/[t]`); the model is told it can only use tool results; questions outside the ticker set get "not covered". Guardrails from P4.4.

### P5c (optional): MCP server
Expose the same read-only tools as an MCP server (`papertrail/mcp_server.py`) so Claude Desktop or other agents can query PaperTrail. Small once P5a/P5b tools exist.

---

## 10. Phase P6: polish (≈3–5 h)

- [ ] README: live URL at the top, "Lite vs Full mode" section, both architecture diagrams, measured precision, cost per run.
- [ ] Screenshots: dashboard, contradiction card with tool trace, `/ask` answering a question, `/status`. (Covers the M6 screenshot item too.)
- [ ] Short demo GIF of `/ask`.
- [ ] Update `CLAUDE.md` and `docs/next-steps.md` to describe the lite deployment.
- [ ] Add a license file.
- [ ] Remaining M6 items for full mode (threshold tuning, real-CIK Form 4 check) can now be done against the lite pipeline's real data, which is easier than with the Docker stack.

---

## 11. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Neon 1 GB fills up | Medium | §6 storage budget; measure on 3 tickers first; drop `raw_text`; `halfvec`; prune claims. Paid tier or second project if needed. |
| Yahoo (yfinance) blocks or rate-limits GitHub runner IPs | Medium | `prices` table means only a few days fetched per night; retry with backoff; fallback source (e.g. Stooq CSV) behind the same interface. |
| SEC EDGAR rate limits | Low | Already have a real User-Agent; keep ≤10 requests/s; incremental ingest. |
| Nightly job too slow | Low–Medium | Cache models; batch NLI (P1.5); `--max-filings`; split stages into separate jobs if needed. |
| LLM cost runs away | Low | Hard spend limit in the Anthropic Console; per-run pair cap; per-IP + daily caps on `/ask`; cache verdicts. |
| Prompt injection via filing text | Low–Medium | Existing tag neutralization; read-only tools; no tool can write or reach the network beyond the DB. |
| Vercel function time limit cuts off `/ask` | Medium | Stream responses; cap tool rounds; fast indexed queries. Verify Hobby limits before building. |
| Full mode drifts from lite mode | Medium | Shared core package (P3.1); CI runs core tests once for both. |
| Public repo exposes secrets | Low | All secrets in GitHub/Vercel secret stores; `.env` stays ignored; CI fails on committed `.env`. |

---

## 12. Decisions

### Open (need Ketaki's call)
| # | Question | Recommendation |
|---|---|---|
| D1 | Keep full Docker mode working on the shared core, or freeze it at a tag? | Keep it working via the shared core package; it's the interview story. Freeze only if time is short. |
| D2 | Neon or Supabase? | Neon. |
| D3 | Which LLM for the checker and `/ask`? Requires an Anthropic API key with a spend cap. | Claude Haiku-class for both; make it configurable. |
| D4 | Search on Vercel: full-text only, or also semantic via ONNX MiniLM? | Full-text first; add semantic if time allows. |
| D5 | Ticker set and history window. | ~25 tickers, 2 years; expand after measuring size. |
| D6 | Keep Neo4j anywhere live? | No; local full mode only. AuraDB free later if a graph view is wanted. |

### Made
| Date | Decision | Why |
|---|---|---|
| 2026-10-29 | Live system = Vercel + Neon + GitHub Actions nightly batch; no Docker in production | Fits free tiers; filings don't need real-time processing |
| 2026-10-29 | Fix correctness bugs (P1) before anything goes public | Duplicate rows inflate severity and counts on a public page |
| 2026-10-29 | Build an eval set before the LLM checker | Otherwise the agent's value can't be shown |

---

## 13. How to keep this documented

- **`docs/worklog.md`**: append one dated entry per working session: what was done, commands run, numbers measured (timings, row counts, DB size, precision, cost), problems hit, next step. Newest entry at the top.
- **This plan**: tick checkboxes as items land; move decisions from "Open" to "Made" with a date; update the effort table if estimates turn out wrong.
- **PRs**: one per phase (or sub-phase), title `P1.1: dedupe contradictions`, description links to the plan section.
- **`CLAUDE.md`**: update §12–§13 when a phase finishes, so the next session starts with accurate context.
