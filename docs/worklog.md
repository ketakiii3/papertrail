# PaperTrail worklog

One dated entry per working session, newest first. Record what was done, commands run, numbers measured, problems hit, and the next step. The plan lives in `docs/lite-deploy-plan.md`.

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
