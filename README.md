# Strava AI Chat

A RAG-powered conversational AI that lets you query and analyze your personal Strava running data using natural language.

Ask questions like *"How does my pace compare to last year?"* or *"Plan a training schedule for next month based on my recent runs"* and get answers grounded in your actual activity history.

## Architecture

```
                ┌──────────────────┐
                │  React + Vite UI │
                └────────┬─────────┘
                         │  POST /api/chat
                         ▼
            ┌────────────────────────────┐
            │   FastAPI (app/main.py)    │
            └────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │         RAG Pipeline               │
        │                                    │
        │  1. Embed user query               │
        │     (text-embedding-3-small)       │
        │                                    │
        │  2. pgvector cosine search         │
        │     top_k = 10                     │
        │     ⊕ merge 5 most-recent runs     │
        │                                    │
        │  3. Build context + summary stats  │
        │                                    │
        │  4. Call GPT-4o with system prompt │
        └────────────────┬───────────────────┘
                         │
                         ▼
                ┌─────────────────┐
                │   LLM response  │
                └─────────────────┘

   ┌────────────────────────────────────────────┐
   │  Background sync (APScheduler, every 6h)   │
   │   Strava API → PostgreSQL → embed new rows │
   └────────────────────────────────────────────┘
```

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy, APScheduler
- **Vector store:** PostgreSQL 16 + pgvector
- **LLM / Embeddings:** OpenAI `text-embedding-3-small` (1536 dims) + `gpt-4o`
- **Frontend:** React + Vite
- **Deployment:** Docker Compose

## Example Conversations

> **You:** What was my longest run, and how did it feel?
>
> **Assistant:** Your longest run was a 32.4 km trail run on Oct 12, 2025 ("Mountain Loop"), completed in 3h 47min at an average pace of 7:01/km. Your average heart rate was 152 bpm and total elevation gain was 840 m — given your typical long-run HR of ~145 bpm, this one pushed you a bit harder than usual, likely due to the climbing.

> **You:** How does my pace this month compare to three months ago?
>
> **Assistant:** In the last 30 days you've averaged 5:42/km across 8 runs (62 km total). Three months ago you were averaging 5:58/km — that's a ~16 sec/km improvement. Most of the gain came on shorter weekday runs; your long runs are still in the 6:10–6:20 range, which is a healthy training pattern.

> **You:** Suggest a training plan for next month based on my data.
>
> **Assistant:** Based on your current weekly volume (~18 km/week, 3 runs) and your recent pace progression, here's a 4-week build...

## RAG Pipeline Design Notes

**Why natural-language descriptions instead of structured fields for embeddings?**
Each Strava activity is rendered into a single human-readable sentence (date, name, sport type, distance, duration, pace, elevation, heart rate, suffer score) and embedded as a whole. This lets the model match on semantic intent like *"my fastest 5K"* or *"hilly long runs"* without needing query parsers or per-field filters. Structured fields are still kept in the same row and surfaced into the prompt context, so the LLM gets exact numbers to cite.

**Retrieval.** User query → `text-embedding-3-small` → pgvector cosine distance against the `activities.embedding` column → top **k = 10**. Cosine was chosen over L2 because it's scale-invariant and works well with OpenAI embeddings.

**Recency merge.** Pure semantic search misses time-anchored questions like *"my latest run"*, because the most recent activity isn't always the most semantically similar to the query. To fix this, the top-10 retrieval is unioned with the 5 most-recent activities (deduplicated by ID) before being passed to the LLM. The most recent run is explicitly tagged in the prompt so the model never substitutes a similar-but-older run.

**Context construction.** Retrieved activities are sorted newest-to-oldest, formatted into a numbered list with date / distance / pace / similarity score / full description, and combined with **global summary stats** (total runs, total distance, yearly breakdown, last 6 months of monthly aggregates). The summary stats let the LLM answer aggregation questions ("how much have I run this year?") without needing every row in context.

**System prompt.** Instructs GPT-4o to cite exact numbers from the context, treat the run tagged `[MOST RECENT]` as authoritative for "latest run" questions, and respond as a data-aware running coach. `temperature = 0.3` for stable, factual answers.

**Background sync.** APScheduler runs every 6 hours (configurable), refreshes the Strava OAuth token, fetches activities newer than the latest one in the DB (incremental), inserts new runs, and embeds them in batches of 20.

## Quick Start

```bash
# 1. Clone
git clone <repo-url> && cd strava-ai

# 2. Configure environment variables
cp .env.example .env
# Edit .env and fill in Strava + OpenAI credentials (see "Strava OAuth" below)

# 3. Start everything (Postgres + API + frontend)
docker-compose up --build

# 4. Open in browser
# Frontend:    http://localhost:3000
# API docs:    http://localhost:8000/docs
# Healthcheck: http://localhost:8000/health
```

The first time the API starts it will immediately run a Strava sync, then re-sync every `SYNC_INTERVAL_HOURS` (default 6).

### Strava OAuth (one-time setup)

1. Create a Strava API application at https://www.strava.com/settings/api (set Callback Domain to `localhost`).
2. Put `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET` into `.env`.
3. Visit http://localhost:8000/auth to get an authorization URL, complete the OAuth flow in your browser.
4. Copy the returned `STRAVA_ACCESS_TOKEN` and `STRAVA_REFRESH_TOKEN` into `.env` and restart the API.

### Local development (without Docker)

```bash
# Backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (in another terminal)
cd strava-chat-ui
npm install
npm run dev
```

### Manual data sync

```bash
# Trigger an incremental sync via the API
curl -X POST http://localhost:8000/api/sync

# Or force a full re-fetch of all activities
curl -X POST "http://localhost:8000/api/sync?full=true"
```

## Project Structure

```
strava-ai/
├── app/
│   ├── main.py              # FastAPI entrypoint + scheduler
│   ├── core/config.py       # Pydantic settings
│   ├── db/
│   │   ├── database.py      # DB engine + init
│   │   └── models.py        # SQLAlchemy models (Activity, ChatHistory)
│   ├── services/
│   │   ├── strava.py        # Strava API client
│   │   ├── sync.py          # Incremental sync + description builder
│   │   ├── embedding.py     # OpenAI embedding generation
│   │   ├── rag.py           # Vector retrieval + context assembly
│   │   └── chat.py          # System prompt + chat orchestration
│   └── api/
│       └── chat.py          # Chat API route
├── strava-chat-ui/          # React + Vite frontend
├── scripts/
│   ├── test_retrieval.py    # Manual retrieval-quality probe
│   └── test_chat.py         # Manual chat-quality probe
├── tests/                   # pytest unit tests
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Tests

```bash
pytest tests/
```
