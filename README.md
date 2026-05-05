# AD Craft

AD Craft is an ad-copy generation and evaluation system built around template retrieval, LLM generation, and human preference feedback.

It combines:
- A Python/FastAPI backend for generation and evaluation APIs
- A React frontend for generation and voting workflows
- An offline pipeline that prepares template and eval-task artifacts
- Docker Compose for local deployment

## Core Features

- Template-based generation
- Retrieves candidate ad templates with semantic search (ChromaDB + embeddings)
- Generates structured template variants and direct free-form ad copy

- Human preference collection
- Serves pairwise evaluation tasks
- Accepts votes (`a`, `b`, `tie`) and resolves tasks by majority/max-vote rules

- Ranking feedback loop
- Periodically refits Bradley-Terry scores from resolved evaluation data
- Uses updated scores to improve candidate ranking

- Runtime artifact sync
- On backend startup, syncs `pipeline/data` artifacts into runtime SQLite + ChromaDB

## Tech Stack

- Backend: Python 3.14, FastAPI, Uvicorn, SQLite (`aiosqlite`)
- Retrieval: ChromaDB + OpenAI embeddings
- Generation: OpenAI API
- Frontend: React + TypeScript + Vite + Nginx
- Deployment: Docker Compose

## Repository Layout

```text
.
├── backend/                  # FastAPI service
├── frontend/                 # React app + Nginx config
├── pipeline/                 # Offline artifact generation scripts
├── pipeline/data/            # Generated artifacts consumed by backend
├── data/                     # Runtime data (SQLite, ChromaDB, images)
├── docker-compose.yml
└── .env.sample
```

## Environment Configuration

1. Copy the sample env file:

```bash
cp .env.sample .env
```

2. Fill in at least:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Optional runtime variables used by backend:
- `OPENAI_CHAT_MODEL` (default: `gpt-5.5`)
- `OPENAI_EMBEDDING_MODEL` (default: `text-embedding-3-small`)
- `OPENAI_IMAGE_MODEL` (default: `gpt-image-2`)
- `ADFRAME_BT_REFIT_INTERVAL` (default: `600`)
- `ADFRAME_EVAL_MAX_VOTES` (default: `5`)
- `ADFRAME_CHROMA_COLLECTION` (default: `ad_templates`)

## Docker Deployment (Recommended)

### Prerequisites

- Docker Engine + Docker Compose plugin
- A valid `OPENAI_API_KEY` in `.env`
- Existing pipeline artifacts in `pipeline/data/` (for example `ds0_templates.json`, `ds0_eval_tasks.json`)

### Build and Start

```bash
docker compose up --build -d
```

### Service Endpoints

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Stop

```bash
docker compose down
```

### View Logs

```bash
docker compose logs -f backend frontend
```

## Runtime Behavior in Docker

Compose mounts:
- `./data -> /app/data` (read/write runtime state)
- `./pipeline/data -> /app/pipeline_data` (read-only artifacts)

At startup, backend will:
1. Initialize DB schema
2. Load/sync artifacts from `pipeline/data`
3. Build retriever state
4. Start periodic Bradley-Terry refit task

## Main API Groups

- Generation
- `POST /api/generate/find-templates`
- `POST /api/generate/direct`
- `POST /api/generate/template-variant`
- `POST /api/generate/template-regenerate-full`
- `POST /api/generate/template-apply-instructions`

- Evaluation
- `GET /api/eval/next`
- `POST /api/eval/submit`
- `GET /api/eval/stats`

## Notes

- Do not commit `.env`.
- Rotate keys immediately if exposed.
- If you refresh offline artifacts, restart backend to trigger sync:

```bash
docker compose restart backend
```
