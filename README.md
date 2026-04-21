# PaperTrail

PaperTrail ingests SEC filings for S&P 500 names, extracts structured **claims**, detects **contradictions** between claims (vector similarity + NLI), optionally enriches with **insider (Form 4)** context, and exposes results through a **FastAPI** backend and **Next.js** dashboard. A **Neo4j** graph mirrors claims and contradiction edges for exploration.

## Architecture (high level)

| Layer | Role |
|--------|------|
| **edgar-ingester** | Pulls filings from EDGAR, stores text in Postgres, emits `filing.new` |
| **claim-extractor** | Sections → candidate claims → FinBERT sentiment → embeddings → `claims.extracted` |
| **contradiction-detector** | Similar claims (pgvector) → NLI → tool-orchestrated agent pipeline → Ollama narrative → Postgres + `contradiction.found` |
| **graph-builder** | Syncs claims and contradictions to Neo4j |
| **api-server** | REST + WebSocket feed |
| **dashboard** | UI at `:3000` |

Contradiction detection includes explicit **agent tools** (semantic compare, NLI, temporal check, insider context, severity) with log lines prefixed `[AGENT]` and `[AGENT_TOOL]` in the detector service. See `docs/docker-dashboard-notes.md` for URLs, Ollama sizing, Neo4j queries, and troubleshooting.

## Prerequisites

- **Docker** and **Docker Compose**
- For full ingestion: a valid **SEC EDGAR** user agent string (email-style) in `.env` per [SEC fair access](https://www.sec.gov/os/webmaster-faq#code-support)

## Quick start (full stack)

```bash
cp .env.example .env
# Edit .env: set EDGAR_USER_AGENT to something like "YourName contact@yourdomain.com"

docker compose up --build
```

Then open:

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 (`neo4j` / `papertrail123`) |
| Ollama | http://localhost:11434 |

Pull the configured Ollama model once (default in `.env.example` is a small model suitable for CPU):

```bash
docker compose exec ollama ollama pull tinyllama
```

## Dashboard only (mock API, no backend)

From `dashboard/`:

```bash
npm install
npm run dev
```

Leave `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` **unset** so the app uses built-in Next.js route handlers with sample data (`src/app/api/v1/...`).

## Viewing agent tool logs

```bash
docker compose logs -f contradiction-detector
```

## Repository layout

```
├── dashboard/          # Next.js UI
├── services/           # Python workers + api-server
├── shared/             # DB, Redis, LLM helpers
├── infra/              # Postgres schema (init.sql)
├── docs/               # Local Docker / API notes
└── docker-compose.yml
```

## License

No license file is included in this repository; add one if you intend to distribute or accept contributions.
