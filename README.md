# LinkedIn Agentic Platform (Distributed Systems Project)

A LinkedIn-style platform with member and recruiter workflows, event-driven analytics, and AI-assisted hiring features.

This repository contains:
- A consolidated backend API (`services/platform-api`) built with FastAPI
- A separate AI service (`ai-agents`) for career coach and hiring assistant flows
- A React frontend (`client`)
- Infrastructure services via Docker Compose (MySQL, MongoDB, Redis, Kafka)

## Tech Stack

- **Frontend:** React
- **Backend:** FastAPI (Python)
- **AI Service:** FastAPI + LLM client
- **Databases:** MySQL, MongoDB, Redis
- **Messaging:** Kafka
- **Orchestration:** Docker Compose

## Repository Structure

```text
.
├── ai-agents/                  # AI workflows and skills service
├── client/                     # React frontend
├── databases/                  # MySQL/Mongo init + seed scripts
├── docs/                       # API docs and architecture diagrams
├── infrastructure/             # Benchmarks, scripts, k8s manifests
├── kafka/                      # Topic config/scripts
├── performance/                # Benchmark scripts
├── redis/                      # Redis config
├── services/
│   └── platform-api/           # Main application API
├── docker-compose.yml
└── .env.example
```

## Architecture Overview

1. Frontend sends API requests to `platform-api`.
2. `platform-api` handles domain modules (members, recruiters, jobs, applications, connections, messaging, analytics, posts).
3. `platform-api` publishes and consumes Kafka events.
4. `ai-agents` service runs AI workflows and is proxied through `/agents/*` and `/skills/*`.
5. Data is distributed across:
   - MySQL (core entities and transactions)
   - MongoDB (event logs, messaging documents)
   - Redis (caching)

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- Python 3.10+ (only if running seed/benchmarks locally outside containers)

## Quick Start

### 1) Configure environment

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

If you use Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### 2) Start all services

```bash
docker-compose up --build
```

### 3) Open the app

- Frontend: [http://localhost](http://localhost)
- Platform API: [http://localhost:3000/docs](http://localhost:3000/docs)
- AI service docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Kafka UI: [http://localhost:8080](http://localhost:8080)

## Seed Data

Run the seed script after stack startup:

```bash
python databases/seed.py --fast
```

For larger dataset:

```bash
python databases/seed.py
```

## Core API Areas

`platform-api` routers:
- `/members/*`
- `/recruiters/*`
- `/jobs/*`
- `/applications/*`
- `/connections/*`
- `/threads/*`, `/messages/*`
- `/analytics/*`, `/events/*`
- `/posts/*`
- `/agents/*`, `/skills/*` (proxied to AI service)

See detailed contract: `docs/api-document.md`

## AI Features

Implemented in `ai-agents`:
- Career coach recommendations
- Hiring assistant workflow (start/status/approve/cancel)
- Resume parsing and candidate matching skills

Env vars for AI/LLM are documented in `.env.example`.

## Benchmarks

- Main benchmark entry: `performance/benchmarks/benchmark_api.py`
- Supporting benchmark assets: `infrastructure/benchmarks/`

## Project Documentation

- `docs/PROJECT_KNOWLEDGE_TRANSFER_SIMPLE.md`
- `docs/PROJECT_KNOWLEDGE_TRANSFER_LLM.md`
- `docs/diagrams/system-architecture.md`
- `docs/diagrams/agent-architecture.md`
- `docs/diagrams/database-schema.md`
- `docs/kafka-topics.md`

## Team Workflow (8 Members)

Recommended:
- 1 feature branch per person (domain-based split)
- Keep pull requests small and focused
- Merge in this order when possible:
  1. schema/config updates
  2. backend endpoints
  3. frontend integration
  4. docs/benchmark updates

Branch naming:
- `feature/<area>-<short-description>`
- Example: `feature/jobs-search-filters`

Commit style:
- `feat(scope): ...`
- `fix(scope): ...`
- `refactor(scope): ...`
- `docs(scope): ...`

## Troubleshooting

- If services fail at startup, check container health:
  ```bash
  docker-compose ps
  ```
- Rebuild clean if needed:
  ```bash
  docker-compose down -v
  docker-compose up --build
  ```
- Verify `.env` values, especially DB credentials and `JWT_SECRET`.

## License

Academic group project (DATA 236).  
Use and extend for educational purposes.
