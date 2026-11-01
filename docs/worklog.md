# PaperTrail worklog

One dated entry per working session, newest first. Record what was done, commands run, numbers measured, problems hit, and the next step. The plan lives in `docs/lite-deploy-plan.md`.

---

## 2026-11-01: PR #1 merged; checker agent with LangChain (T1–T4); Facebook case

**Done**
- Merged PR #1 (`fix/correctness`) into `main` (merge commit `6f8573c`). Auto-merge is disabled on the repo; merged once the only unchecked change was docs.
- Branch `agent/tool-calling`: a real tool-calling agent. LangChain 1.x `create_agent` on `ChatOllama`, verdict as a `ToolStrategy` schema (`submit_verdict`), `ToolCallLimitMiddleware` (3) + `ModelCallLimitMiddleware`, forced structured-output fallback, 3 company-scoped read-only tools. New service `contradiction-checker` (own consumer group on `contradiction.found`), migration 003 (`agent_runs` + verdict columns), `contradiction.verified` topic, API verdict fields + `/contradictions/{id}/trace`, `scripts/facebook_case.py`.
- New verdict label `materialized_risk` after testing the Facebook case (below).
- Code guardrails added after the first real runs: severity forced low unless real/materialized_risk; evidence citing uncalled tools dropped; blank args treated as not given; topic values listed in the tool description. Prompt bumped to `checker-v2`.

**Measured** (Apple M5 Max, native Ollama, temperature 0)
- Both contradictions stored in the dev DB are false positives on reading them: Costco (NLI 0.81, "high") pairs an exhibit reference with an accounting-policy cross-reference; P&G (NLI 0.70) pairs a market-share sentence with an 8-K header, and tinyllama's narrative invented a reason it mattered.
- Checker on those two: mistral 7B (v1 prompt) scope / noise, 0 tool calls, 21 s / 6 s; llama3.2 3B (v2) noise / noise, 3 / 1 tool calls, 3.3 s / 2.4 s. Rules severity was "high" for both. Every run ended `forced`: mistral answers in prose and never calls tools; llama3.2 calls tools but sends `submit_verdict` with only the label.
- Facebook 2018 (SEC 2019-140): 10-K 2018-02-01 "users' data may be improperly accessed, used, or disclosed" vs 10-Q 2018-04-26 "the misuse of certain data by a developer". Claim filter drops both sentences; MiniLM cosine 0.72 (retrieval would find it); DeBERTa NLI neutral 1.00, contradiction 0.00. The 10-Q still repeats the 10-K sentence verbatim.
- Checker on Facebook: llama3.2 read both contexts and answered `materialized_risk` with the first v2 tool descriptions; after adding the topic list to one tool description, 3/3 runs say `noise` (1 tool call). mistral: 3/3 `noise`, though its rationale says the risk materialized. Deterministic at temperature 0; brittle to wording.
- Tests: 60 passed (12 checker unit tests with a scripted fake model, 2 checker DB tests).

**Problems**
- Ollama has no "tool call required" option, so a model that answers in prose can only be rescued by the forced structured-output call. The forced rate is a model-quality metric for T5.
- `rpk topic consume --num N` blocks until N messages exist; use `timeout 5 rpk ...`.

**Decisions**
- LangChain over the hand-rolled loop in the plan (Ketaki's call). Kafka consumer group over Celery for the checker. `contradiction_id` as the agent_runs key.
- Not tuning the prompt to the Facebook case: one example is a test case, not a training set.

**Next**
- `ollama pull qwen3:4b` and rerun the two stored pairs + `scripts/facebook_case.py`.
- E1–E3: the labeled eval set, so T5 can say whether the checker beats the rules. Include materialized-risk pairs (Facebook, the 2024 SEC cyber cases).
- T6: show verdict + trace in the dashboard; consume `contradiction.verified` in the API feed and graph-builder.

---

## 2026-10-30 (later): Dev-DB migration, real Form 4 re-ingest, F6 timing

**Done**
- Backed up the dev DB (`pg_dump -Fc`, 2.8 MB, kept outside the repo), then ran `scripts/migrate.py` on it. Applied 001 + 002; a second run says "schema up to date".
- Fixed the Form 4 download URL (`form4_xml_url`): filing documents are on `www.sec.gov/Archives/...`, not `data.sec.gov`, and `primaryDocument` (`xslF345X06/form4.xml`) is the XSL-rendered HTML; the raw XML is `form4.xml` one level up. **Every Form 4 download 404'd before this**, which is the real reason no real Form 4 run ever stored rows (CLAUDE.md §13 item 4). Unit test added.
- Local-only `docker-compose.override.yml` (gitignored) maps compose Postgres to `127.0.0.1:55433`, because a native Postgres on the Mac holds 5432.

**Measured**
- Migration on dev DB: contradictions 3 rows → 2 (1 duplicate pair removed); insider rows 2 → 2, hand-seeded `S`/`P` normalized to `sell`/`buy`; surveillance flags 2 → 2.
- Re-ingest AAPL (CIK 320193, last 40 submissions) twice: run 1 stored **80** rows, run 2 stored **0**; total stays 82. `insider.new` published 80 times, then 0.
- AAPL code mix: S 35, M 22, A 13, F 9, G 2, P 1. Of 57 disposals (`D`), only 34 are open-market sales ($111.9M); the old A/D rule would have called all 57 "sells" ($241.3M), more than doubling the insider-selling signal.
- Backfill dry run for AAPL selects 34 transactions (36 open-market − 2 already flagged); the 46 `other` rows are skipped.
- F6, NLI only (cross-encoder/nli-deberta-v3-base, CPU in Docker; Apple M5 Max, 64 GB, Docker 18 CPUs / 6.2 GB), same pairs both ways, two rounds each:
  | Workload | Old: per pair, sync on loop | New: batched per claim, `to_thread` |
  |---|---|---|
  | ADBE filing 24, 7 real candidate pairs | 5.1–7.2 pairs/s, loop stall 371–563 ms | 9.1–9.2 pairs/s, stall 5–6 ms |
  | XOM filing 47 × 20 nearest claims (any company), 800 pairs | 4.9–6.7 pairs/s (120–163 s), stall 789–949 ms | 10.8–12.0 pairs/s (67–74 s), stall 11–12 ms |
  The dev data has few companies with more than one filing, hence the second, synthetic-pairing workload for throughput.

**Not done**
- Surveillance tasks for the 80 new AAPL rows not run (consumer/worker not started); `surveillance.flag` follow-through still unverified.

**Next**
- Merge PR #1, then E1 (eval sampling). Optionally start the full stack and run the AAPL backfill for real.

---

## 2026-10-30: Fixes F0–F8 on `fix/correctness`

**Done**
- F0: `scripts/migrate.py` + `infra/migrations/` (tracked in `schema_migrations`; migrations also folded into `init.sql`, which pre-marks them applied). Root `conftest.py` aliases the hyphenated service folders; `pytest.ini`; `requirements-test.txt`; `tests/db/` fixtures that create a throwaway database per test.
- F1: migration 001 (dedupe + `uq_contradiction_pair` on LEAST/GREATEST). `insert_contradiction` → `ON CONFLICT DO NOTHING`, returns `None` on no-op; detector skips publish then. Pre-check is batched: `existing_contradiction_partners(claim_id, ids)` drops known pairs before any NLI/LLM work.
- F2: migration 002 adds `accession_number`, `line_no`, unique index on them; `shares` → `NUMERIC(18,4)`. Ingester inserts with `ON CONFLICT (accession_number, line_no)`. Pre-migration rows (no accession) are *adopted* on re-ingest instead of duplicated (`_adopt_legacy_row`).
- F3: `classify_transaction`: P → buy, S → sell, else other; raw `transaction_code` + `acquired_disposed` stored. `summarize_insider_rows` counts open-market only. Surveillance consumer + backfill only run event studies for buy/sell. Decision logged in `docs/surveillance-plan.md`.
- F4: all root tests now collect and run. 4 pre-existing tests had never run and failed against the code; fixed the code, not the tests: `\brestructur\b` / `\bacqui\b` never matched "restructuring" / "acquisition"; "could materially ..." wasn't classed as risk; "increased our dividend" was topic `growth` not `capital`; "Vice President" was detected as "President".
- F5: `.github/workflows/ci.yml` (pytest incl. db tests on a pgvector service container; dashboard lint + build; advisory pip-audit / npm audit). README badge.
- F6: detector scores NLI once per new claim (`asyncio.to_thread(score_pairs, ...)`) in the same (older, newer) order the agent uses; agent takes `nli=`. FinBERT + MiniLM in claim-extractor also moved to `asyncio.to_thread`. `CrossEncoder` import made lazy so tests don't need torch.
- F7: demo-mode routes `/api/v1/surveillance/flags` and `/flags/[id]` (placeholder insider names). Neo4j `CONTRADICTS` direction comment. `.gitignore` globs.
- F8: README (idempotency, migrations, tests), `CLAUDE.md` §3/§4/§13, plan checkboxes.

**Measured**
- Tests: 43 passed (37 without DB + 6 DB tests against a throwaway `pgvector/pgvector:pg16` container). Previously: root tests didn't collect; 8 surveillance tests ran only in Docker.
- Dev DB (`papertrail_postgres-data`, read-only count before migrating): 803 claims, 76 filings, contradictions 3 rows / 2 distinct pairs (→ 1 duplicate), 2 insider rows (both hand-seeded with types `P` / `S`), 2 surveillance flags.
- Dashboard: `npm run lint` clean, `npm run build` passes. Surveillance panel + drawer checked in demo mode in a browser (table, BUY/SELL, AR chart, α/β/R²).

**Problems found along the way**
- Dashboard `SurveillancePanel` compared `transaction_type` to `"P"`/`"S"` (the seeded values), so real ingested `buy`/`sell` rows would all have shown as red non-buys. Now uses buy/sell; migration 002 normalizes the hand-seeded `P`/`S` rows.
- Panel list URL was `/surveillance/flags&limit=50` (no `?`) when "flagged only" was off → 404 → empty panel. Fixed.
- The old parser passed float `shares` into a `BIGINT` column; asyncpg likely rejected those inserts (swallowed by the `except`), which may be why no real Form 4 run ever produced rows. Not confirmed; check during the real-CIK run.
- A native Postgres on the Mac holds `127.0.0.1:5432`, so `docker compose up postgres` fails to bind. Read the dev volume through a port-less temporary container instead.

**Not done**
- Migration not applied to the dev volume yet; manual re-ingest check (plan §2 "Manual check") not run.
- F6 timing before/after (needs the model images + a filing).
- PR #1 not opened.

**Next**
- Apply `scripts/migrate.py` to the dev DB, re-ingest one ticker twice, confirm counts match; record F6 timings. Then open PR #1 and start E1.

---

## 2026-10-30: Deployment options + fixes/tool-calling plan

**Done**
- Compared lower-friction ways to host PaperTrail → `docs/deployment-options.md`. Recommendation changed from "Neon + nightly GitHub Actions" (now option C) to **option A: static JSON snapshot on Vercel**, with the pipeline run locally on the existing Docker stack. One production service, no database, no storage cost.
- Wrote `docs/fixes-and-tool-calling-plan.md`: fixes F0–F8, eval set E1–E3, tool calling T1–T8, with file paths, migrations, tests, and acceptance checks.
- Added a status note at the top of `docs/lite-deploy-plan.md` pointing to the two new docs.

**Measured / checked (free tiers, 2026-10-30)**
- Oracle Always Free Arm: cut to 2 OCPU / 12 GB (from 4 / 24) effective 2026-06-15; idle instances (<20% CPU/net/mem over 7 days) can be reclaimed. Rules out running the 14-container stack there.
- Hugging Face Spaces: Docker Spaces need a paid plan for personal accounts; free disk is not persistent.
- Supabase free: 500 MB DB, projects pause after 1 week of inactivity (third-party summary).
- Turso free: 1 GB, 3 databases (third-party summary).

**New bug found**
- Form 4 parser treats every disposal (`D`) as a "sell" and every acquisition (`A`) as a "buy". That includes tax withholding (`F`), gifts (`G`) and option exercises (`M`/`X`), not just open-market trades (`S`/`P`). This inflates insider-selling signals. → Plan F3.
- `shares` is parsed as a float but stored in a `BIGINT` column; fractional shares will fail or truncate. → Plan F2.

**Decisions**
- Fixes come before the eval set, and the eval set before the checker agent.
- Pending Ketaki: Q1 (Anthropic API key with spend cap), Q3 (deployment option A), Q4 (ship chat in v1 or later).

**Next**
- F0: create `fix/correctness`, add the migration runner and `conftest.py`.

---

## 2026-10-29: Review + lite deployment plan

**What happened**
- Reviewed the local repo against GitHub (`ketakiii3/papertrail`). Local `main` = `origin/main` = `d85ca2f` ("Close M6, audit security posture, ship Phase 1+2 hardening"). Working tree clean.
- No Vercel project exists for PaperTrail yet; nothing is deployed.
- Wrote `docs/lite-deploy-plan.md` (phases P0–P6) and this worklog. Added a pointer in `CLAUDE.md` §17.

**Checks run (in a clean cloud checkout, no Docker)**
- Dashboard: `npm ci && npx next build` → **passes** (9 static pages, `/` = 207 kB first load).
- Surveillance tests: `pytest services/surveillance/tests` with `surveillance` on `PYTHONPATH` → **8 passed**.
- Root tests (`tests/`): **don't collect**. A hardcoded `/Users/ketaki.dabade/papertrail` path, and imports from hyphenated folders (`models/severity-scorer`, `services/transcript-ingester`).
- Full Docker stack: **not run** (no Docker available in the review environment). Last documented end-to-end run is 2026-04-26 with seeded AAPL data.

**Bugs found**
1. `contradictions` has no unique key and `insert_contradiction` has no `ON CONFLICT`, so redelivered Kafka messages or out-of-order backfills store duplicate pairs. README claims idempotency for this path. → Plan P1.1.
2. `insider_transactions` has no unique constraint, so `ON CONFLICT DO NOTHING` in `form4_parser.py` never fires. Re-ingestion duplicates trades, causing duplicate surveillance tasks and inflated insider-sell totals that can wrongly raise severity. → Plan P1.2.
3. The agent pipeline scores NLI one pair at a time, synchronously inside the async loop (`score_pairs` already supports batches). → Plan P1.5.
4. Dashboard mock mode has no `/api/v1/surveillance/flags` route, so the surveillance panel is empty in demo mode. → Plan P1.6.

**Observations**
- The current "agent" is a fixed sequence of five Python functions; the LLM (tinyllama) only writes a summary at the end. Real tool calling is planned in P5.
- No measurement of contradiction precision exists. → Plan P2.

**Hosting facts checked today**
- Neon free plan: 1 GB storage/project, 100 CU-hours/project/month, autosuspend after 5 min, pgvector included, no card (neon.com/pricing).
- GitHub Actions: standard runners free and unlimited for public repos; public `ubuntu-latest` = 4 CPU / 16 GB RAM / 14 GB SSD (docs.github.com).

**Next step**
- Ketaki to answer open decisions D1–D6 in the plan (§12).
- Then start P0/P1 on branch `lite/p1-fixes`.
