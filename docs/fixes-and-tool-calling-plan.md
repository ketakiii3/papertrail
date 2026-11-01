# PaperTrail: plan for the fixes and real tool calling

**Written:** 2026-10-30. **Status:** F0–F8 done on `fix/correctness` and in PR #1 (not merged); dev DB migrated, AAPL re-ingest check and F6 timing recorded in the worklog. E and T not started.
**LLM decision (2026-10-30):** local only for now. Small models via Ollama, no hosted API. Default `qwen3:4b`; see §4.0.
**Scope:** correctness fixes (F1–F8), a small evaluation set (E1–E3), and real LLM tool calling (T1–T8). Deployment is a separate decision; see `docs/deployment-options.md`. Everything here works with the existing Docker stack and doesn't depend on how it's deployed.
**Log every session in `docs/worklog.md`** (template in §6).

---

## 1. Order of work

| Step | ID | What | Effort | Branch |
|---|---|---|---|---|
| 1 | F0 | Branch, migration runner, test scaffolding | 1–2 h | `fix/correctness` |
| 2 | F1 | Dedupe contradictions | 1–1.5 h | ″ |
| 3 | F2 | Dedupe insider transactions | 1–1.5 h | ″ |
| 4 | F3 | Classify Form 4 trades correctly (open-market only) | 1 h | ″ |
| 5 | F4 | Make all tests runnable | 1 h | ″ |
| 6 | F5 | CI on GitHub Actions | 0.5–1 h | ″ |
| 7 | F6 | Batch NLI, stop blocking the event loop, skip known pairs | 1–2 h | ″ |
| 8 | F7–F8 | Small fixes, docs | 0.5–1 h | ″ → PR #1 |
| 9 | E1–E3 | Evaluation set + baseline precision | 4–6 h | `eval/baseline` → PR #2 |
| 10 | 4.0, T1–T2 | Native Ollama + small model; LLM tool-loop + tool registry | 3–4 h | `agent/tool-calling` |
| 11 | T3–T4 | Checker agent + schema | 3–4 h | ″ |
| 12 | T5 | Score the agent on the eval set | 1–2 h | ″ |
| 13 | T6 | Show verdicts + tool traces in the dashboard | 2–3 h | ″ → PR #3 |
| 14 | T7 | "Ask PaperTrail" chat | 5–8 h | `agent/ask` → PR #4 |
| 15 | T8 | (Optional) MCP server | 2 h | `agent/mcp` |

≈ 27–40 h total. The fixes (PR #1) come first because the duplicates distort everything downstream, including the eval and the agent's inputs.

**Rule for every step:** a unit test that fails before and passes after, an entry in the worklog, and the checkbox ticked here.

---

## 2. Fixes

### F0. Setup
- [x] `git switch -c fix/correctness`
- [x] **Migration runner.** `infra/init.sql` only runs on a fresh Postgres volume, so schema changes to an existing database need migrations:
  - `infra/migrations/NNN_name.sql`, applied in order
  - `scripts/migrate.py`: creates `schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)`, applies anything missing, each file in its own transaction
  - Run: `docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" -v "$(pwd)/infra:/app/infra" api-server python -m scripts.migrate`
  - Also fold each migration into `init.sql` so fresh installs match
- [x] **Test database.** DB-level tests (F1, F2) need Postgres with pgvector. Use the compose `postgres` service locally and a `pgvector/pgvector:pg16` service container in CI. Mark them `@pytest.mark.db`.

### F1. Duplicate contradictions
**Bug:** `contradictions` has no unique key; `insert_contradiction` (`shared/db.py`) has no `ON CONFLICT`. Kafka redelivery (at-least-once) or out-of-order backfills store the same pair again, and each duplicate also publishes another `contradiction.found` to the dashboard and Neo4j.

- [x] `infra/migrations/001_contradiction_pair_unique.sql`
  ```sql
  DELETE FROM contradictions c USING contradictions d
  WHERE c.id > d.id
    AND LEAST(c.claim_a_id, c.claim_b_id)    = LEAST(d.claim_a_id, d.claim_b_id)
    AND GREATEST(c.claim_a_id, c.claim_b_id) = GREATEST(d.claim_a_id, d.claim_b_id);

  CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_pair
    ON contradictions ((LEAST(claim_a_id, claim_b_id)), (GREATEST(claim_a_id, claim_b_id)));
  ```
- [x] `insert_contradiction`: add
  `ON CONFLICT ((LEAST(claim_a_id, claim_b_id)), (GREATEST(claim_a_id, claim_b_id))) DO NOTHING RETURNING id` and return `None` when nothing was inserted. Change the return type to `int | None`.
- [x] `detector.py`: `if contra_id is None: continue` before `publish("contradiction.found", ...)`.
- [x] Add `contradiction_exists(a, b)` in `shared/db.py` *(built as batched `existing_contradiction_partners(claim_id, other_ids)`)*; call it in `detector.py` **before** `evaluate_contradiction_pair` so redelivered messages don't redo NLI and LLM work.
- [x] Test `tests/db/test_contradiction_dedupe.py`: insert (a,b), then (a,b), then (b,a) → 1 row, second and third calls return `None`.
- [x] Record in the worklog how many duplicate rows the migration deleted on your local DB (`SELECT COUNT(*) ...` before/after). *2026-10-30: 3 rows → 2 (1 duplicate).*

### F2. Duplicate insider transactions
**Bug:** `insider_transactions` has no unique constraint, so the `ON CONFLICT DO NOTHING` in `form4_parser.py` never fires. Re-running Form 4 ingestion duplicates trades → duplicate surveillance tasks and inflated `sell_count` / `total_sell_value` in `summarize_insider_rows`, which can **wrongly bump a contradiction's severity**.

- [x] `infra/migrations/002_insider_txn_unique.sql`
  ```sql
  ALTER TABLE insider_transactions
    ADD COLUMN IF NOT EXISTS accession_number VARCHAR(25),
    ADD COLUMN IF NOT EXISTS line_no INT;

  -- dedupe legacy rows that have no accession number
  DELETE FROM insider_transactions t USING insider_transactions u
  WHERE t.id > u.id
    AND t.company_id = u.company_id AND t.insider_name = u.insider_name
    AND t.transaction_date = u.transaction_date AND t.transaction_type = u.transaction_type
    AND t.shares IS NOT DISTINCT FROM u.shares AND t.price IS NOT DISTINCT FROM u.price;

  CREATE UNIQUE INDEX IF NOT EXISTS uq_insider_txn_line
    ON insider_transactions (accession_number, line_no)
    WHERE accession_number IS NOT NULL;
  ```
  Deleting a transaction cascades to its `surveillance_flags` row, which is what we want for duplicates.
- [x] `form4_parser.py`: `parse_form4_xml` returns transactions in document order; in `ingest_company_form4`, loop with `enumerate(transactions)` and insert `f["accession_number"]` and `line_no`. Change to `ON CONFLICT (accession_number, line_no) WHERE accession_number IS NOT NULL DO NOTHING`.
- [x] Check while there: `shares` is parsed as `float` but the column is `BIGINT`. Fractional shares (common with dividend reinvestment) will fail or truncate. Use `NUMERIC(18,4)` in the migration, or round deliberately.
- [x] Test with a saved Form 4 XML fixture (`tests/fixtures/form4_sample.xml`): ingest twice → same row count; `publish` mock called once per transaction.

### F3. Form 4 trade classification
**Bug:** the parser maps any disposal (`D`) to `"sell"` and any acquisition (`A`) to `"buy"`. Form 4 disposals include tax withholding on vested stock (code `F`), gifts (`G`), and option-related moves (`M`, `X`) that aren't open-market trades. Counting those as "insider selling" adds noise to both surveillance and the insider-escalation rule.

- [x] Store the raw code: `ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS transaction_code VARCHAR(2)` (in migration 002).
- [x] Classify: code `S` → `sell`, `P` → `buy`, everything else → `other` (keep `acquired_disposed` too).
- [x] `summarize_insider_rows` and `get_insider_context` count only `sell`/`buy`; report `other` separately.
- [x] Surveillance (`consumer.py` / `backfill.py`) only enqueues event studies for `buy`/`sell`.
- [x] Note in `docs/surveillance-plan.md` decision log: "event studies run on open-market trades only (codes P/S)".
- [x] Test: fixture with one `S`, one `F`, one `M` → 1 sell, 2 other; `large_insider_sales` ignores the `F` row.

### F4. Make all tests runnable
**Bug:** root tests hardcode `sys.path.insert(0, "/Users/ketaki.dabade/papertrail")` and import from hyphenated folders (`services/claim-extractor`, `services/transcript-ingester`, `models/severity-scorer`), which Python can't import. Surveillance tests only import inside the Docker image.

- [x] Root `conftest.py` that registers import aliases for the hyphenated folders:
  ```python
  # conftest.py
  import importlib.util, sys
  from pathlib import Path
  ROOT = Path(__file__).parent
  sys.path.insert(0, str(ROOT))

  def _alias(name: str, path: Path):
      spec = importlib.util.spec_from_file_location(
          name, path / "__init__.py", submodule_search_locations=[str(path)])
      mod = importlib.util.module_from_spec(spec)
      sys.modules[name] = mod
      spec.loader.exec_module(mod)

  _alias("claim_extractor", ROOT / "services/claim-extractor/src")
  _alias("transcript_ingester", ROOT / "services/transcript-ingester/src")
  _alias("surveillance", ROOT / "services/surveillance/src")
  _alias("severity_scorer", ROOT / "models/severity-scorer")   # add __init__.py there
  ```
- [x] Update test imports (`from claim_extractor.splitter import ...`, etc.) and delete the hardcoded paths.
- [x] `pytest.ini`: `testpaths = tests services/surveillance/tests`, markers `db`, `models`.
- [x] Tests that need model weights get `@pytest.mark.models` and are skipped in CI by default.
- [x] **Done when** `pytest -q -m "not db and not models"` passes from the repo root on a laptop with no Docker.

### F5. CI
`.github/workflows/ci.yml`, on push and pull request:
- [x] Job `python`: Python 3.11, install a light `requirements-test.txt` (numpy, pandas, scipy, statsmodels, pydantic, pytest, asyncpg, lxml, bs4; no torch) → `pytest -q -m "not models"`, with a `pgvector/pgvector:pg16` service container for `db` tests.
- [x] Job `dashboard`: Node 20, `npm ci && npm run lint && npm run build` in `dashboard/`.
- [x] Non-blocking: `pip-audit`, `npm audit --audit-level=high`.
- [x] README badge.

### F6. NLI batching and event loop
**Problem:** `agent.py` calls `check_negation` once per pair, and the model runs synchronously inside async code, blocking the consumer's event loop (Kafka heartbeats included). `score_pairs` already accepts a list.

- [x] In `detector.py`, per new claim: fetch candidates → drop pairs that already exist (F1) → `await asyncio.to_thread(score_pairs, all_pairs)` once → pass each pair's NLI result into `evaluate_contradiction_pair` (add an `nli` parameter so it doesn't recompute).
- [x] Same `asyncio.to_thread` treatment for FinBERT and MiniLM calls in `claim-extractor/pipeline.py`.
- [x] Measure seconds per filing before and after on the same filing; record in the worklog. *NLI ~1.6–2.5× faster; worst event-loop stall ~0.9 s → ~12 ms.*

### F7. Small fixes
- [x] Dashboard mock mode: add `src/app/api/v1/surveillance/flags/route.ts` and `[id]/route.ts` with sample data, so the panel isn't empty in demo mode. (If you choose deployment option A, the `DataSource` work replaces mocks anyway; then skip this.)
- [x] Neo4j `CONTRADICTS` is MERGEd with a direction; with F1 ordering (older = A) it stays consistent. Add a comment saying so.
- [x] `.gitignore`: `**/.DS_Store`, `**/__pycache__/`.

### F8. Docs for PR #1
- [x] README: the "handlers are idempotent" sentence is now true; mention migrations and `scripts/migrate.py`.
- [x] `CLAUDE.md` §3 (data model) and §13 (open items): new columns, constraints, migration runner.
- [x] Worklog entry with duplicate counts removed, timings from F6, test counts.
- [x] Open PR #1 `fix/correctness` → `main`. (https://github.com/ketakiii3/papertrail/pull/1)

**Manual check on the Docker stack (you run this; it can't be done from a Claude session without Docker):**
```bash
docker compose up -d --build
docker compose run --rm ... python -m scripts.migrate
# re-run ingestion twice for one ticker, then:
docker compose exec postgres psql -U papertrail -c "SELECT COUNT(*), COUNT(DISTINCT (LEAST(claim_a_id,claim_b_id), GREATEST(claim_a_id,claim_b_id))) FROM contradictions;"
docker compose exec postgres psql -U papertrail -c "SELECT COUNT(*), COUNT(DISTINCT (accession_number, line_no)) FROM insider_transactions;"
# both pairs of numbers should match
```

---

## 3. Evaluation set (needed before the agent)

The agent's job is to throw out false positives. Without labeled pairs there's no way to show that it does.

### E1. Sample
- [ ] `eval/sample_pairs.py`: from the deduplicated `contradictions`, sample ~150 stored pairs stratified by severity and topic, plus ~50 pairs that scored just under the NLI threshold (0.45–0.6) to estimate misses. Write `eval/pairs_unlabeled.csv` with both claims' text, context, dates, sections, ticker, and the current pipeline's severity.

### E2. Label
- [ ] Label in a spreadsheet; save as `eval/pairs.csv`. One label per pair:
  - `real`: the company's stance or facts genuinely changed in a way an analyst would care about
  - `update`: a number or forecast was revised; worth tracking, not a contradiction
  - `boilerplate`: hedged risk language ("may", "could") vs. a statement of fact
  - `scope`: different segment, product, geography or period
  - `noise`: bad sentence split, table fragment, header
- [ ] Freeze a split: 50 dev (for prompt tuning) / 150 test (never looked at while tuning). Store the split column in the CSV.

### E3. Baseline
- [ ] `eval/run_eval.py --system rules`: precision of "flagged = real" overall and by severity, a confusion table vs. labels, recall on the near-threshold sample.
- [ ] Record the numbers in the worklog and at the top of this file. This is the number the agent has to beat.

---

## 4. Real tool calling

### What changes
Today `agent.py` runs `semantic_compare → check_negation → temporal_check → get_insider_context → severity_score` in a fixed order, then asks tinyllama for a paragraph. The model never picks a tool and can't change the outcome.

After this work: the fast deterministic filter stays (pgvector + NLI decide *which* pairs are worth a look), then an LLM **investigates each candidate with tools of its choosing** and returns a structured verdict that decides whether and how the pair is shown.

### 4.0 Local model setup (decided 2026-10-30: local LLM only, small model)

**Why not tinyllama:** it has no tool-calling support, so it can't run this agent at all.

**Candidates** (all on Ollama with tool support; compare them on the eval set in T5 and keep the best one that fits your RAM):
| Model | Download | Why try it |
|---|---|---|
| `qwen3:4b` (**default**) | ~2.5 GB | Tied for top score among small models in a 2026 small-LLM tool-calling benchmark |
| `qwen3:1.7b` | ~1.4 GB | Fallback if RAM is tight |
| `qwen2.5:7b` | ~4.4 GB | Step up: ~98% schema-correct tool calls in one benchmark; needs more RAM |
| `phi4-mini:3.8b` | ~2.5 GB | Second small option with good benchmark results |
| ~~`llama3.2:3b`~~ | 2.0 GB | Skip: ~78% schema-correct calls, unreliable beyond a single tool |

(Download sizes are approximate; check with `ollama list` after pulling.)

**Run Ollama natively on the Mac, not in Docker.** Docker on macOS has no GPU access, so models in the `ollama` container run on CPU only. Native Ollama uses Apple's Metal GPU and is much faster. Then:
- `brew install ollama` (or the Mac app), `ollama pull qwen3:4b`
- In `.env`: `OLLAMA_URL=http://host.docker.internal:11434`, `OLLAMA_MODEL=qwen3:4b`
- Remove or comment out the `ollama` service in `docker-compose.yml` (keep it behind a compose profile for Linux machines).
- This also frees Docker Desktop memory, which the OOM notes in `docker-dashboard-notes.md` say is tight.

**Designing for a small model** (small models get worse with many tools, long chains, and vague descriptions):
- **≤ 5 tools** for the checker (§T2 is trimmed to that).
- **≤ 3 tool calls per pair**, then force the verdict.
- Give the model the pre-filter results (NLI scores, dates, gap, insider summary) **up front** so it only calls tools for extra evidence.
- Short system prompt, one-sentence tool descriptions, explicit argument formats (`YYYY-MM-DD`).
- `temperature: 0`, `num_ctx: 8192`.
- For Qwen3, try with thinking off (`"think": false` in the Ollama request) for speed, and on, for accuracy; keep whichever scores better in T5.
- **Validate everything.** Parse tool calls and the verdict with Pydantic. If a call is malformed: one retry with the validation error fed back, then fall back to the rules result. If the model never calls `submit_verdict`, make a final request with Ollama's `format` set to the verdict JSON schema (structured output) to get a valid verdict without tools.
- Log the malformed-call rate per model; it's part of the T5 comparison.

**Speed:** local inference takes seconds per call, so the checker must not run inside the Kafka consumer's loop. Run it as a **Celery task** (`verify_contradiction`) on its own queue, reusing the existing Celery setup. This also closes deferred item #2 in `docs/security-audit.md` (Ollama backpressure in the contradiction detector). The detector stores the pair with `verdict = NULL`, enqueues the task, and the task fills in the verdict and publishes an update.

### T1. Tool loop (`shared/agent_loop.py`)
A small, provider-agnostic loop:
```python
async def run_tool_loop(
    system: str,
    user: str,
    tools: list[ToolSpec],          # name, description, JSON schema, async handler
    final_tool: str = "submit_verdict",
    max_tool_calls: int = 3,
    provider: LLMProvider = default_provider(),
) -> LoopResult:                    # final_args, trace[], tokens_in/out, latency_ms, stop_reason
```
- Each turn: send messages + tool schemas → if the model asks for tools, run the handlers (in parallel when it asks for several), append the results, repeat.
- Stop when the model calls `final_tool`, or after `max_tool_calls` (then force it with tool choice set to `submit_verdict`).
- Every call is logged as `[AGENT_TOOL] name args → result (truncated)`, keeping the current log style.
- Tool results are truncated (e.g. 2,000 chars) and wrapped as data, reusing `_neutralize_tags` from `shared/llm.py`, since filing text is untrusted.
- **Provider:** `OllamaProvider` only, using Ollama's `/api/chat` with the `tools` field; model from `OLLAMA_MODEL` (default `qwen3:4b`, §4.0). Keep a small `LLMProvider` interface so a hosted model could be added later without touching the agent, but don't build one now.
- Ollama unreachable or model missing → skip the agent and keep the rules-based result, same as today's behavior.

### T2. Tool registry (`services/contradiction-detector/src/agent_tools.py`)
Wrap the existing functions and add a few. All **read-only** and **scoped to the pair's company**; the handler injects `company_id`, so the model can't ask about other companies.

Five tools, because small models get worse with more (§4.0). NLI isn't a tool: its scores are already in the pre-filter digest the model starts with.

| Tool | Arguments | Returns | Source |
|---|---|---|---|
| `get_claim_context` | `claim_id` | sentence, ±2 neighbouring sentences, section, form, filed date | new (uses `filings.raw_text`) |
| `find_related_claims` | `topic?`, `date_from?`, `date_to?`, `limit ≤ 5` | other claims from this company on that topic, with dates | wraps `get_similar_claims` / topic filter |
| `get_insider_trades` | `date_from`, `date_to` | open-market trades (after F3), summary, and each trade's event-study result if one exists | `get_insider_transactions_between` + `summarize_insider_rows` + `surveillance_flags` |
| `get_price_move` | `date_from`, `date_to` | stock vs SPY return over the window | reuses `surveillance/market_data.py` |
| `submit_verdict` | see T3 | ends the loop | — |

Tool results are kept short (a few hundred tokens each) so they fit in a small model's context alongside the claims.

### T3. Checker agent (`agent.py`)
- [ ] Keep steps 1–5 as the **pre-filter and starting evidence**. Give the model the two claims, dates, sections, and the pre-filter digest.
- [ ] System prompt (versioned as `CHECKER_PROMPT_V1`): you're checking whether two statements from the same company's SEC filings really conflict; investigate with tools only as needed; common false positives are hedged risk language, different scope, and routine updates; cite evidence; finish with `submit_verdict`.
- [ ] `submit_verdict` schema:
  ```json
  {
    "verdict": "real | update | boilerplate | scope | noise",
    "severity": "low | medium | high | critical",
    "confidence": 0.0,
    "rationale": "2–4 sentences, citing claim ids and tool results",
    "evidence": [{"tool": "get_insider_trades", "finding": "..."}]
  }
  ```
  Labels match the eval labels (E2), so it can be scored directly.
- [ ] Guardrails: ≤ 3 tool calls per pair; a cap on pairs checked per filing (`AGENT_MAX_PAIRS_PER_FILING`) so a huge 10-K can't tie up the machine for hours; never re-check a pair already checked with the same prompt version + model; on any error fall back to the rules result with `verdict = NULL`.
- [ ] Runs as the Celery task `verify_contradiction` (§4.0), not inside the Kafka consumer.
- [ ] The rationale replaces the tinyllama paragraph in `agent_reasoning`.

### T4. Schema (`infra/migrations/003_agent_runs.sql`)
```sql
CREATE TABLE IF NOT EXISTS agent_runs (
  id SERIAL PRIMARY KEY,
  claim_a_id INT REFERENCES claims(id) ON DELETE CASCADE,
  claim_b_id INT REFERENCES claims(id) ON DELETE CASCADE,
  provider TEXT, model TEXT, prompt_version TEXT,
  trace JSONB NOT NULL,          -- [{tool, args, result_preview, ms}]
  verdict JSONB,                 -- submit_verdict args
  tokens_in INT, tokens_out INT, latency_ms INT,
  stop_reason TEXT,              -- verdict | max_calls | error
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE contradictions
  ADD COLUMN IF NOT EXISTS verdict VARCHAR(12),
  ADD COLUMN IF NOT EXISTS agent_confidence FLOAT,
  ADD COLUMN IF NOT EXISTS agent_run_id INT REFERENCES agent_runs(id);
```
- [ ] Decide whether non-`real` verdicts are still stored (recommended: yes, with the verdict, so the UI can show "filtered out" and the eval can use them).
- [ ] Add `verdict` to the `contradiction.found` Kafka payload and to the Neo4j `CONTRADICTS` edge.

### T5. Does it help?
- [ ] `eval/run_eval.py --system agent --model <name> --split test`: precision (verdict = real vs. label = real), confusion table, average tool calls, malformed-call rate, seconds per pair.
- [ ] Run it for each model in §4.0 that fits your RAM (at least `qwen3:4b` and `qwen3:1.7b`; `qwen2.5:7b` if possible), with Qwen3 thinking on and off.
- [ ] Compare against the E3 baseline. Tune the prompt on the **dev** split only.
- [ ] Record a results table here, in the worklog, and in the README, e.g.:
  | System | Precision | Malformed calls | Sec/pair |
  |---|---|---|---|
  | Rules only | X% | — | — |
  | + qwen3:4b checker | Y% | a% | s |
  | + qwen2.5:7b checker | Z% | b% | t |
- [ ] Write down your machine (chip, RAM) next to the timings so they mean something.

### T6. Dashboard
- [ ] `ContradictionCard`: verdict pill, confidence, and a "How was this checked?" expander that lists the tool calls in order (tool, arguments, short result) and the rationale.
- [ ] Feed defaults to `verdict = real` (plus unchecked), with a toggle to show filtered pairs.
- [ ] API: `GET /api/v1/contradictions/{id}/trace` → the `agent_runs` row.

### T7. "Ask PaperTrail" (chat over the data)
- [ ] **Runs locally for now**, because the model is local: a FastAPI endpoint `POST /api/v1/ask` in `api-server` that runs the T1 loop against Ollama and streams steps back (server-sent events). The dashboard's `/ask` page calls it when the local stack is running.
- [ ] Tools (5, SQL-backed): `search_claims(query, ticker?, topic?, date_from?, date_to?)`, `get_contradictions(ticker, severity?, verdict?)`, `get_timeline(ticker, date_from, date_to)`, `get_insider_trades(ticker, date_from, date_to)` (includes surveillance flags), `get_agent_trace(contradiction_id)`.
- [ ] UI: chat box on `/ask`; each tool call shows as a collapsible step while it runs; answers cite claim and filing links.
- [ ] Rules in the system prompt: answer only from tool results, cite ids, say "not covered" for companies outside the dataset.
- [ ] Guardrails: max 4 tool calls per question, max output tokens, request timeout.
- [ ] **On the public static site** (deployment option A) there's no local model, so `/ask` shows **recorded runs** instead: run 5–8 good example questions locally, save each full trace (question, tool calls, results, answer) into the snapshot, and render them as replayable examples labelled "recorded locally with qwen3:4b". Live chat on the public site can come later if you add a hosted model.

### T8. (Optional) MCP server
- [ ] `services/mcp-server/` exposing the T7 tools over MCP (Python `mcp` SDK), so Claude Desktop or any MCP client can query PaperTrail. Small once T7's tools exist. Good to mention alongside the in-app agent.

---

## 5. Open decisions

| # | Decision | Recommendation |
|---|---|---|
| Q1 | ~~Anthropic API key?~~ **Decided 2026-10-30: no. Local Ollama only, small model.** | — |
| Q2 | Store non-`real` verdicts or drop them? | Store with verdict. |
| Q3 | Deployment option (see `deployment-options.md`) | A: static snapshot, for now. |
| Q4 | Public `/ask`: recorded example runs only, or add a hosted model later? | Recorded runs for now. |
| Q5 | How much RAM does your Mac have? Decides whether `qwen2.5:7b` is worth testing. | — |

---

## 6. Documentation rules

- **`docs/worklog.md`**: one entry per session, newest first:
  ```
  ## YYYY-MM-DD: <short title>
  **Done:** what changed (files, migrations, PRs)
  **Measured:** counts, timings, sizes, precision, cost
  **Problems:** what broke and how it was fixed or worked around
  **Decisions:** anything decided (also copy to the plan's decision table)
  **Next:** the next concrete step
  ```
- **This file**: tick checkboxes as items land; put eval numbers at the top once known.
- **`CLAUDE.md`**: update §3, §4, §13 when a PR merges, so the next session starts from accurate context.
- **PR descriptions** reference the step IDs (`F1`, `T3`, ...).
