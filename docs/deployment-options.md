# PaperTrail: deployment options compared

**Written:** 2026-10-30. Free-tier numbers were checked on this date (sources at the end); recheck them before signing up for anything.
**Related:** `docs/lite-deploy-plan.md` (the original Neon + GitHub Actions plan, now option C below), `docs/fixes-and-tool-calling-plan.md`, `docs/worklog.md`.

---

## TL;DR

**Start with option A, a static snapshot.** Run the pipeline on your own machine (the Docker stack as it is today), export the results to a JSON file, and deploy only the dashboard to Vercel. There's no database account, nothing to keep awake, nothing that gets paused or reclaimed, and no storage bill. The data is as fresh as your last export, and the page says so.

Move to option C (Neon + nightly GitHub Actions) only if you later want it to update itself every night. The dashboard is built against a small `DataSource` interface so that switch doesn't mean rewriting pages.

---

## The options

| | Option | Running cost | Storage limit | Moving parts in production | Main risks | Friction |
|---|---|---|---|---|---|---|
| **A** | **Static JSON snapshot on Vercel** (pipeline runs on your laptop) | $0 (+ LLM API for `/ask`, capped) | Only what you export; aim < 10 MB | 1 (Vercel) | Data goes stale; repo bloat if the snapshot is large | **Lowest** |
| B | Snapshot as a read-only SQLite file bundled with the site | $0 | Same as A; SQLite handles larger exports | 1 | Native module (`better-sqlite3`) in serverless; bundle-size limits | Low |
| C | Neon Postgres + nightly GitHub Actions + Vercel | $0 | 1 GB per project | 3 | 1 GB fills up; Yahoo/EDGAR blocking CI IPs; secrets in two places | Medium |
| D | Supabase instead of Neon in C | $0 | 500 MB per project | 3 | **Free projects pause after 1 week of inactivity**; smaller DB | Medium–High |
| E | Turso (hosted SQLite) instead of Neon in C | $0 | 1 GB | 3 | Rewrite pgvector SQL for Turso's vector syntax | High |
| F | Oracle Cloud Always Free VM running Docker Compose as-is | $0 | 200 GB block | 14 containers you operate | **Cut to 2 OCPU / 12 GB in June 2026**; idle instances get reclaimed; "out of capacity" errors; you own security patching | High |
| G | Hugging Face Spaces | — | 50 GB, **not persistent** | — | **Docker Spaces now need a paid plan** for personal accounts | Not viable for free |

### Why not F (run the whole thing on a free VM)?
It looks like the least work because nothing changes in the code. But Oracle halved the Always Free Arm allowance to 2 OCPU / 12 GB (effective June 15, 2026). Your 14 containers plus FinBERT, DeBERTa NLI, MiniLM and Ollama won't fit comfortably; your own `docker-dashboard-notes.md` already records Ollama out-of-memory problems on a laptop. Oracle also reclaims Always Free instances that sit below 20% CPU/network/memory for 7 days, which a demo site will, and you'd be exposing a VM you have to patch and secure.

### Why not D (Supabase)?
Half the storage of Neon (500 MB), and a free project pauses after a week without activity, so a portfolio link could be dead when a recruiter clicks it.

---

## Option A in detail (recommended)

```
your laptop                                  Vercel (Hobby)
───────────                                  ──────────────
docker compose up  (as today)                Next.js dashboard
  ingest → claims → contradictions             reads dashboard/data/snapshot.json
  → checker agent → Form 4 → surveillance      (server components, no DB)
        │                                    /ask → Claude tool-use loop
        ▼                                      over the same snapshot data
python scripts/export_snapshot.py
  → dashboard/data/snapshot.json  ──git push──►  auto-deploy
```

### What goes in the snapshot
Only what the pages show, not the whole database:
- `meta`: exported_at, git SHA, ticker list, pipeline thresholds, eval precision
- `companies`: the tickers you processed
- `contradictions`: every stored pair with both claims' text, context, dates, section, filing URL, severity, verdict, and the agent's tool trace
- `stats` and `severity_counts`, precomputed
- `insider_transactions` and `surveillance_flags` (with daily AR for the drawer chart) for the processed tickers
- `timeline` per company: filing list (form, date, URL) + contradiction dates
- Optional `claims_index`: claim text + topic + date only (no embeddings), capped per company, for `/ask` search

No embeddings, no raw filing text. Measure the file after the first export and record it in the worklog. If it grows past ~10 MB, gzip it or switch to option B.

### Steps
1. **`scripts/export_snapshot.py`**: reads Postgres, writes `dashboard/data/snapshot.json`, validates it against a JSON schema, prints the size.
2. **`dashboard/src/lib/data/`**: a `DataSource` interface (`getStats`, `getLatestContradictions`, `getCompany`, `getTimeline`, `getSurveillanceFlags`, `searchClaims`, ...) with two implementations:
   - `SnapshotSource` (reads the JSON; used on Vercel)
   - `ApiSource` (calls FastAPI; used with the local Docker stack)
   Pick one with `DATA_SOURCE=snapshot|api`. This replaces the current mock route handlers, which become unnecessary.
3. **Pages switch to the interface.** The live WebSocket feed is hidden in snapshot mode; a "Data as of <date>" badge shows instead.
4. **Search in snapshot mode** filters `claims_index` by keywords/topic/date in memory. Good enough at this size.
5. **Deploy:** create the Vercel project with root directory `dashboard`, set `DATA_SOURCE=snapshot`. Pushes to `main` redeploy.
6. **Refresh:** whenever you want new data, run the pipeline, export, commit, push. A one-line `make snapshot` can wrap this.

### Risks and what to do about them
| Risk | Mitigation |
|---|---|
| Stale data | "Data as of" badge; refresh monthly or before you share the link. |
| Snapshot too big for git | Keep < 10 MB; gzip; or move to Vercel Blob / a GitHub release asset; or option B. |
| `/ask` costs money | Hard monthly spend limit in the Anthropic Console; per-IP and daily caps; max tool rounds and tokens. Or ship without `/ask` first. |
| Leaking something private | The snapshot only holds public SEC data. Never export `watchlist` emails. The export script has an allowlist of tables. |
| Prompt injection through filing text in `/ask` | Tools are read-only over the snapshot; filing text is wrapped as data (same approach as `shared/llm.py`). |

### Moving from A to C later
Implement a `PostgresSource` behind the same interface, stand up Neon, and add the nightly workflow from `lite-deploy-plan.md` §8. No page changes.

---

## Sources (checked 2026-10-30)
- Neon free plan: https://neon.com/pricing (1 GB/project, 100 CU-hours/project, 5-min autosuspend, pgvector)
- GitHub-hosted runners: https://docs.github.com/en/actions/reference/runners/github-hosted-runners (public repos free; 4 CPU / 16 GB)
- Oracle Always Free resources: https://docs.oracle.com/iaas/Content/FreeTier/resourceref.htm (2 OCPU / 12 GB A1; idle reclamation rules)
- Oracle cut, June 2026: https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/
- Hugging Face Spaces: https://huggingface.co/docs/hub/spaces-overview (Docker Spaces need a paid plan; 50 GB non-persistent disk)
- Supabase free tier summary: https://automationatlas.io/answers/supabase-free-tier-limits-2026/ (500 MB, pauses after 1 week; third-party summary, confirm on supabase.com/pricing)
- Turso summary: https://devradar-dev.github.io/open-research/databases/turso (1 GB, 3 DBs; third-party summary)
