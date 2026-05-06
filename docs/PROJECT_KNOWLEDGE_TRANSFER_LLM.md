# LinkedIn Simulation + Agentic AI: Complete Technical Knowledge Transfer

This document is the canonical technical handover for this repository. It is designed for both engineers and LLM agents that need full context of architecture, data model, service boundaries, event flows, and operational behavior.

## 1) Project Purpose and Scope

This project implements a LinkedIn-like hiring/networking platform using distributed systems patterns:

- 3-tier architecture (Client -> Services/Kafka -> Datastores)
- Domain microservices in Node.js/Express
- Agentic AI microservice in FastAPI
- Kafka for asynchronous workflows and event analytics
- Polyglot persistence: MySQL + MongoDB + Redis
- Docker Compose deployment for local distributed runtime

Primary product domains:

- Member and recruiter profiles
- Job posting and search
- Job applications and workflow status
- Messaging and connections
- Analytics dashboards
- Agentic AI workflows for shortlist generation and recruiter assistance

## 2) Repository Structure

Top-level modules:

- `client`: React web UI
- `services`: Node/Express microservices and API gateway
- `ai-agents`: FastAPI-based agentic AI service + skills
- `databases`: MySQL and MongoDB initialization scripts + seeding
- `kafka`: Kafka setup/helpers
- `performance`: benchmark scripts (100-thread scenarios)
- `docs`: API docs and topic docs
- `docker-compose.yml`: full system orchestration

## 3) Runtime Architecture

Service runtime (as configured in `docker-compose.yml`):

- API Gateway: `:3000`
- Profile Service: `:3001`
- Job Service: `:3002`
- Application Service: `:3003`
- Messaging Service: `:3004`
- Connection Service: `:3005`
- Analytics Service: `:3006`
- AI Agent Service (FastAPI): `:8000`
- Kafka: `:9092` (internal), `:29092` (host)
- Kafka UI: `:8080`
- MySQL: host `:3307` -> container `:3306`
- MongoDB: host `:27019` -> container `:27017`
- Redis: `:6379`

## 4) Request and Event Flow Model

### 4.1 Synchronous path

1. Client sends REST request to API Gateway.
2. Gateway validates auth (JWT where applicable) and routes to target microservice.
3. Service reads/writes datastore and returns response.
4. Hot-read endpoints use Redis cache when available.

### 4.2 Asynchronous path

1. Domain service emits Kafka event using standard event envelope.
2. One or more consumers process event (analytics logging, state mutation, AI trigger).
3. Results may be persisted in MySQL/MongoDB and optionally pushed to client via polling/WebSocket endpoint.

### 4.3 AI orchestrated path

1. Recruiter starts hiring workflow via AI API.
2. AI service publishes `ai.requested` on `ai.requests`.
3. AI consumer receives request and runs multi-step workflow.
4. Workflow writes trace/status/outputs, publishes `ai.results`.
5. UI receives status via `POST /agents/hiring-assistant/status` and WebSocket stream.
6. Recruiter performs human-in-the-loop action (`approve`/`edit`/`reject`).

## 5) Service Responsibilities

- **API Gateway**
  - Unified entrypoint and routing to backend services
  - Security boundary (JWT validation/injection strategy)

- **Profile Service**
  - Members and recruiters CRUD
  - Profile views and profile-related lookup/search
  - Produces `profile.updated`

- **Job Service**
  - Job posting CRUD and search/filter
  - Job view/save/close events and counters
  - Produces job domain topics

- **Application Service**
  - Submit application with transactional consistency
  - Duplicate and closed-job rule enforcement
  - Status transitions and audit trail
  - Produces application topics, consumes `job.closed`

- **Messaging Service**
  - Thread and message lifecycle
  - Stores conversational payloads in MongoDB
  - Produces `message.sent`

- **Connection Service**
  - Request/accept/reject connection lifecycle
  - Maintains accepted connection graph data
  - Produces connection topics

- **Analytics Service**
  - Consumes all relevant domain topics
  - Stores events and generates dashboard metrics

- **AI Agent Service (FastAPI)**
  - Skills: Resume parsing, candidate matching
  - Agents: Hiring assistant, career coach
  - Kafka consumer for `ai.requests` (`group_id=ai-agent-group`)
  - Publishes `ai.results`, stores trace and status lifecycle

## 6) API Surface (High-Level)

Domain API design follows POST-oriented endpoints behind `/api` gateway prefix. Major groups:

- `/members/*`, `/recruiters/*`
- `/jobs/*`
- `/applications/*`
- `/threads/*`, `/messages/*`
- `/connections/*`
- `/events/*`, `/analytics/*`
- `/agents/*`, `/skills/*` (AI)

Reference: `docs/api-document.md`.

## 7) Kafka Topic Contract

Shared event envelope:

```json
{
  "event_type": "job.viewed",
  "trace_id": "uuid",
  "timestamp": "ISO-8601",
  "actor_id": "member_or_recruiter_id",
  "entity": { "entity_type": "job|application|thread|connection|ai_task", "entity_id": "uuid" },
  "payload": {},
  "idempotency_key": "uuid"
}
```

Core topics:

- `profile.updated`
- `job.posted`, `job.viewed`, `job.saved`, `job.closed`
- `application.submitted`, `application.status.changed`
- `message.sent`
- `connection.requested`, `connection.accepted`, `connection.rejected`
- `ai.requests`, `ai.results`

Reference: `docs/kafka-topics.md`.

## 8) Data Architecture and Schema

### 8.1 MySQL (transactional core)

Schema database: `linkedin_ds`.

Key tables:

- Identity/Profile: `members`, `member_skills`, `member_experience`, `member_education`, `recruiters`, `profile_views`
- Jobs: `jobs`, `job_skills`, `saved_jobs`
- Applications: `applications`, `application_notes`, `application_status_history`
- Connections: `connection_requests`, `connections`
- Social Feed extension: `posts`, `post_likes`, `post_comments`, `saved_posts`

Key constraints and indexes:

- Unique member email and recruiter email
- Unique application per `(job_id, member_id)`
- Idempotency keys for retry-safe writes (`applications`, `connection_requests`)
- Fulltext search on jobs (`title`, `description`)
- Location/status/date indexes for search and dashboards

### 8.2 MongoDB (document/event/trace stores)

Database: `linkedin_ds_logs`.

Collections:

- `threads` (participant-centric indexing)
- `messages` (`thread_id + sent_at`, `sender_id`, unique sparse `idempotency_key`)
- `event_logs` (`event_type + timestamp`, `actor_id`, `entity.entity_id`, `trace_id`, unique sparse `idempotency_key`)
- `ai_task_traces` (unique `trace_id`, `status`, recency and history indexes)

### 8.3 Redis (cache layer)

Used for cache acceleration on high-read API paths and gateway/session-adjacent cache usage.

## 9) Reliability and Failure Controls

Implemented business/failure controls:

- Duplicate email/user conflict prevention
- Duplicate application prevention
- Cannot apply to closed job
- Idempotency key protection for retried requests/events
- Async fault isolation with Kafka consumer groups
- Transactional write paths in critical operations

## 10) Performance and Scalability Framework

Benchmark scripts:

- `performance/benchmarks/benchmark_api.py`
- `performance/benchmarks/run_benchmarks.sh`

Benchmark scenarios:

- **Scenario A**: job search + job detail (read-heavy)
- **Scenario B**: application submit (write + event emission)

Comparative stack modes:

- `B` (base)
- `B + S` (SQL cache via Redis)
- `B + S + K` (Kafka-integrated)
- `B + S + K + Other` (index/pooling/etc.)

Target test profile: 100 concurrent users.

## 11) Dataset and Seeding

Dataset files:

- `datasets/raw/jobs.csv`
- `datasets/raw/resumes.csv`

Seed command:

- `python databases/seed.py`

Modes:

- `--fast` for quick local verification
- `--keep` for non-destructive top-up

## 12) AI Agent Architecture Details

Main AI service routes include:

- `POST /agents/hiring-assistant/start`
- `POST /agents/hiring-assistant/status`
- `POST /agents/hiring-assistant/approve`
- `POST /agents/hiring-assistant/cancel`
- `GET /agents/hiring-assistant/evaluation/summary`
- `WS /agents/hiring-assistant/ws/{trace_id}`
- `POST /skills/parse-resume`
- `POST /skills/match-candidates`
- `POST /agents/career-coach`

Task states include:

- `pending`, `running`, `awaiting_approval`, `approved`, `rejected`, `completed`, `failed`, `cancelled`

Behavior notes:

- AI workflow is Kafka-first.
- Inline fallback can run if Kafka unavailable (config-gated).
- Traces are persisted for observability and evaluation summaries.

## 13) Diagrams (Use These Files)

- System architecture diagram: `docs/diagrams/system-architecture.md`
- Agent architecture diagram: `docs/diagrams/agent-architecture.md`
- Database schema diagram: `docs/diagrams/database-schema.md`

## 14) Onboarding Checklist (for New Developers or LLM Agents)

1. Read `docs/api-document.md` and `docs/kafka-topics.md`.
2. Read this file end-to-end.
3. Bring up environment: `docker-compose up --build`.
4. Verify health endpoints and gateway routing.
5. Seed data (`python databases/seed.py --fast` first, full later).
6. Validate one sync flow and one Kafka-backed flow.
7. Validate one full AI hiring workflow and approval cycle.
8. Run performance benchmark scripts and record metrics.

