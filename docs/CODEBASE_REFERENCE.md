# LinkedIn DS — Complete Codebase Reference

## System Overview

This project is a LinkedIn-style professional network platform built as a distributed system for a graduate Data Science course. It demonstrates relational + document databases, event-driven architecture via Kafka, Redis caching, and LLM-powered agentic AI workflows.

**Stack:** Python (FastAPI) · React (SPA) · MySQL · MongoDB · Redis · Apache Kafka · Groq LLM · Docker Compose · Nginx · AWS EC2

**Two backend services:**
- `platform-api` — the main REST API (port 3000 internal, exposed through nginx at `/api/`)
- `ai-agent-service` — agentic AI service (port 8000 internal, exposed through nginx at `/api/agents/`, `/api/skills/`, WebSocket at `/ws/`)

---

## Directory Structure

```
LinkedIn_Project_updated/
├── docker-compose.yml          # Full stack orchestration (9 containers)
├── project.env                 # Environment variable values
├── .env.example                # Template with all required variables
├── requirements.txt            # Root-level Python deps (benchmarking)
├── ai-agents/                  # AI agent FastAPI service
├── client/                     # React SPA + Nginx container
├── databases/                  # DB init scripts + seeder
├── docs/                       # Documentation
├── infrastructure/             # K8s YAML, benchmarks, setup scripts
├── kafka/                      # Topic config + creation script
├── performance/                # Benchmark runner
├── redis/                      # Redis config
└── services/
    └── platform-api/           # Main REST API service
```

---

## Root-Level Files

### `docker-compose.yml`
Orchestrates 9 containers: `zookeeper`, `kafka`, `mysql`, `mongodb`, `redis`, `platform-api`, `ai-agent-service`, and `client`. Defines:
- Named volumes for MySQL and MongoDB persistence
- Healthchecks for all stateful services so dependent containers wait for readiness
- Environment variable injection from `project.env`
- A custom bridge network (`linkedin-net`) so containers resolve each other by name
- The `client` container (Nginx) is the only one with a public port (80); all traffic is proxied through it

### `project.env`
Runtime environment values injected into Docker containers: MySQL credentials, MongoDB credentials, JWT secret, Redis host, Kafka broker, Groq API key and model name, service URLs, feature flags (`RESUME_PARSER_USE_LLM`, `CAREER_COACH_USE_LLM`, `KAFKA_INLINE_FALLBACK`).

### `.env.example`
Template showing every required variable with placeholder values. Used as the starting point when deploying to a new environment.

### `requirements.txt` (root)
Python dependencies for local benchmarking scripts (`httpx`, `asyncio`). Not used inside containers.

---

## `services/platform-api/` — Main REST API

The platform API is a single FastAPI application that consolidates what would be multiple microservices. All traffic from the browser goes through Nginx → `/api/` prefix → this service.

### `services/platform-api/Dockerfile`
Two-stage build: installs Python 3.11-slim, copies `requirements.txt`, runs `pip install`, copies the `app/` directory, and starts the server with `uvicorn app.main:app --host 0.0.0.0 --port 3000 --workers 2`.

### `services/platform-api/requirements.txt`
Key dependencies: `fastapi`, `uvicorn`, `aiomysql` (async MySQL), `motor` (async MongoDB), `redis[asyncio]`, `kafka-python-ng==2.2.2` (Python 3.10+ compatible Kafka client), `httpx` (for the AI proxy), `bcrypt` (password hashing), `PyJWT` (token signing), `python-multipart` (file uploads).

### `app/main.py`
**Entry point.** On startup it:
1. Creates an `aiomysql` connection pool (10 min / 20 max connections) and stores it in `app.state.pool`
2. Creates a `motor` MongoDB client and stores the `linkedin_ds` database in `app.state.mongo`
3. Creates an `aioredis` connection pool and stores it in `app.state.redis`
4. Initializes the `KafkaProducer` for event publishing
5. Starts three Kafka consumer threads: analytics, applications, and connections consumers
6. Registers `AuthStripMiddleware` — validates `Authorization: Bearer <jwt>` on every non-public request and injects `x-member-id` / `x-role` headers for downstream use
7. Registers CORS middleware (all origins allowed)
8. Mounts all routers under the paths matching their service responsibilities

Public paths (no auth): `/members/create`, `/members/login`, `/recruiters/create`, `/recruiters/login`, `/jobs/search`, `/jobs/get`, and all analytics/health endpoints.

### `app/config.py`
Reads all `os.environ` values with fallback defaults. Exports: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DB`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MONGO_URI`, `REDIS_HOST`, `REDIS_PORT`, `KAFKA_BROKER`, `JWT_SECRET`, `AI_AGENT_URL`, `CACHE_TTL` (300 seconds).

### `app/deps.py`
FastAPI dependency injection. Three functions — `pool_dep()`, `mongo_dep()`, `redis_dep()` — read from `request.app.state` and return the connection handles. Exported as annotated type aliases `MysqlPoolDep`, `MongoDep`, `RedisDep` used in router function signatures via `Depends()`.

### `app/common.py`
Shared utilities:
- `uuid4_str()` — generates a UUID4 string
- `jsonable_row(rows)` — converts `aiomysql` dict rows to JSON-safe format (handles `datetime`, `Decimal`, `bytes`)
- `decode_token(token)` — decodes a JWT using `JWT_SECRET`, returns payload dict or `None`
- `trace_id(body, header)` — extracts or generates a trace ID for event correlation
- `make_event_idempotency_key()` — deterministic key preventing duplicate Kafka events
- Defines `PUBLIC_PATHS` set used by `AuthStripMiddleware`

### `app/kafka_bus.py`
**Event bus.** Two responsibilities:

**Publishing:** `publish_event(topic, event_type, actor_id, entity_type, entity_id, payload, trace_id, idempotency_key)` — wraps data in a standard envelope `{event_type, actor_id, entity_type, entity_id, payload, trace_id, idempotency_key, timestamp}` and sends it to Kafka. Uses a module-level `KafkaProducer` singleton initialized lazily.

**Consuming (3 background threads):**
- `_analytics_consumer` — subscribes to all 15 topics (group: `analytics-group`), inserts every event into MongoDB collection `event_logs` with a timestamp. This is the raw event log used by the analytics dashboard.
- `_application_consumer` — subscribes to `job.closed` (group: `application-group`), automatically transitions all `submitted`/`reviewing` applications for that job to `rejected` status in MySQL.
- `_connection_consumer` — subscribes to `connection.accepted` (group: `connection-group`), increments `connections_count` on both members in MySQL.

### `app/routers/members.py`
Member profile management.

| Endpoint | What it does |
|---|---|
| `POST /members/create` | Registers a new member. Hashes password with bcrypt. Inserts into `members` table. Publishes `profile.created` to Kafka. Returns JWT. |
| `POST /members/login` | Validates email + password (bcrypt). Returns JWT valid 7 days. |
| `POST /members/get` | Fetches member profile. Checks Redis cache first (`member:{id}` key, TTL 300s). On miss, queries MySQL, hydrates skills from `member_skills`, saves to Redis. Increments `profile_views_count`, publishes `profile.viewed`. |
| `POST /members/update` | Updates allowed fields (headline, about, skills, location, etc.). Invalidates Redis cache. Publishes `profile.updated`. |
| `POST /members/search` | Full-text LIKE search across `first_name`, `last_name`, `email`, `headline`, `about`, and `CONCAT(first_name, ' ', last_name)`. Optionally joins `member_skills` for skill-based filtering. |
| `POST /members/delete` | Soft-delete (sets `is_deleted=1`). |
| `POST /members/skills/add` | Inserts into `member_skills`. Invalidates Redis cache. |
| `POST /members/skills/remove` | Deletes from `member_skills`. Invalidates Redis cache. |

### `app/routers/recruiters.py`
Recruiter account management. Mirrors member auth pattern but stores data in the `recruiters` table with company-specific fields (`company_name`, `company_industry`, `company_id`).

| Endpoint | What it does |
|---|---|
| `POST /recruiters/create` | Creates recruiter. Generates `company_id` if not provided. Hashes password. Returns JWT. |
| `POST /recruiters/login` | bcrypt password check. Returns JWT with `role: recruiter`. |
| `POST /recruiters/get` | Returns profile (password hash excluded). |
| `POST /recruiters/update` | Updates profile fields. Normalizes `hiring_highlights` (comma-separated string ↔ JSON). |
| `POST /recruiters/search` | LIKE search across name and company fields. |
| `POST /recruiters/delete` | Soft-delete. |

### `app/routers/jobs.py`
Job posting CRUD and search.

| Endpoint | What it does |
|---|---|
| `POST /jobs/create` | Inserts job. Inserts skill rows into `job_skills`. Publishes `job.posted`. |
| `POST /jobs/get` | Fetches job + recruiter company name. Increments `views_count`. Publishes `job.viewed`. |
| `POST /jobs/search` | Filtered search: keyword matches `title`, `skill`, `company_name` (LIKE). Supports `employment_type`, `work_mode`, `seniority_level`, `industry`, `location` filters. Pagination with `page`/`limit` (max 100). Returns `total` count (separate COUNT query). |
| `POST /jobs/close` | Sets `status='closed'`. Publishes `job.closed`. Triggers application cascade rejection via Kafka consumer. |
| `POST /jobs/byRecruiter` | Lists all jobs for a recruiter. |
| `POST /jobs/save` | Saves job for member. Increments `saves_count`. Publishes `job.saved`. |
| `POST /jobs/unsave` | Removes saved job. Decrements `saves_count`. |
| `POST /jobs/savedJobs` | Lists all jobs saved by a member. |
| `POST /jobs/update` | Updates allowed job fields. |

### `app/routers/applications.py`
Job application submission and tracking.

| Endpoint | What it does |
|---|---|
| `POST /applications/submit` | Validates member and job exist. Enforces `UNIQUE(job_id, member_id)`. Inserts application with optional `resume_url`, `resume_text`, `cover_letter`, `answers`. Increments `applicants_count` on job. Publishes `application.submitted`. Uses `idempotency_key` to prevent duplicate submissions. |
| `POST /applications/byJob` | Lists applications for a job (recruiter view). Joins member profile data. |
| `POST /applications/byMember` | Lists all applications for a member. |
| `POST /applications/updateStatus` | Changes application status (submitted → reviewing → interview → offer/rejected). Writes to `application_status_history` audit table. Publishes `application.status.changed`. |

### `app/routers/connections.py`
Professional networking.

| Endpoint | What it does |
|---|---|
| `POST /connections/request` | Validates both users exist (members OR recruiters). Checks for existing connection or pending request (both directions). Inserts into `connection_requests`. Publishes `connection.requested`. |
| `POST /connections/accept` | Moves request to `connections` table (normalized pair). Publishes `connection.accepted`. Consumer increments `connections_count` on both profiles. |
| `POST /connections/reject` | Marks request as rejected. Publishes `connection.rejected`. |
| `POST /connections/list` | Lists accepted connections for a user. Joins member data. |
| `POST /connections/pending` | Lists incoming pending requests. |
| `POST /connections/sent` | Lists outgoing pending requests. |
| `POST /connections/mutual` | Finds members connected to both users (graph intersection query). |

### `app/routers/messaging.py`
Real-time messaging backed by MongoDB.

| Endpoint | What it does |
|---|---|
| `POST /threads/open` | Finds existing thread by sorted participant IDs or creates one. Returns `thread_id`. |
| `POST /threads/get` | Fetches thread metadata. |
| `POST /threads/byUser` | Lists all threads where user is a participant, sorted by `updated_at` desc. Pagination supported. |
| `POST /messages/send` | Validates sender is a participant. Inserts message into `messages` collection. Updates thread's `last_message` and `updated_at`. Publishes `message.sent`. `idempotency_key` field prevents duplicate sends on retry. |
| `POST /messages/list` | Returns messages in a thread, oldest first, with pagination. |

**MongoDB schema:** `threads` collection stores `{thread_id, participant_ids[], last_message, created_at, updated_at}`. `messages` collection stores `{message_id, thread_id, sender_id, message_text, sent_at, idempotency_key}`.

### `app/routers/posts.py`
Social feed (home page content).

| Endpoint | What it does |
|---|---|
| `GET /posts/` | Returns feed posts ordered by `created_at` desc. Joins like/save counts. |
| `GET /posts/saved` | Returns posts saved by a specific member. |
| `POST /posts/` | Creates a new post (type: general, job_update, career_update, etc.). Publishes Kafka event. |
| `POST /posts/{id}/like` | Inserts like. Increments `likes_count`. |
| `DELETE /posts/{id}/like` | Removes like. Decrements `likes_count`. |
| `POST /posts/{id}/save` | Saves post for later. |
| `DELETE /posts/{id}/save` | Removes saved post. |
| `POST /posts/{id}/comments` | Adds a comment. |
| `DELETE /posts/{id}/comments/{cid}` | Deletes comment (author or post owner only). |

### `app/routers/analytics.py`
Analytics dashboard data, all read from the MongoDB `event_logs` collection (populated by the Kafka analytics consumer).

| Endpoint | What it does |
|---|---|
| `POST /analytics/overview` | Aggregates total event counts per event type over a time window. |
| `POST /analytics/jobs/top` | Top jobs by application count from event logs. |
| `POST /analytics/members/active` | Most active members by event count. |
| `POST /analytics/recruiter/dashboard` | Recruiter-specific analytics: top jobs by applications, jobs per month, low-traction jobs, click-through rates, saved jobs trends, city-wise applications, AI agent metrics. |
| `POST /analytics/ai/metrics` | Aggregate AI task metrics: total runs, completion rates, approval rates, shortlist sizes. |

All queries use MongoDB aggregation pipelines (`$match`, `$group`, `$sort`, `$limit`, `$project`).

### `app/routers/ai_proxy.py`
HTTP reverse proxy. All requests to `/agents/{path}` and `/skills/{path}` are forwarded to the AI agent service at `http://ai-agent-service:8000/{path}` using `httpx.AsyncClient`. Headers, query params, and body are forwarded verbatim. Strips `content-encoding`, `transfer-encoding`, and `connection` response headers to prevent decompression conflicts.

---

## `ai-agents/` — AI Agent Service

A separate FastAPI application dedicated to agentic AI workflows. Runs at port 8000, accessed through the platform-api proxy.

### `ai-agents/Dockerfile`
Installs Python dependencies, copies source, starts with `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1`. Single worker to avoid shared-state issues with the in-memory trace store.

### `ai-agents/requirements.txt`
Key deps: `fastapi`, `uvicorn`, `httpx`, `motor` (MongoDB for traces), `redis[asyncio]`, `kafka-python-ng==2.2.2`, `python-multipart` (resume file uploads), `pypdf2`/`python-docx` (document parsing).

### `ai-agents/main.py`
FastAPI entry point. Registers four routers: `resume_parser_router` (prefix `/skills`), `matcher_router` (prefix `/skills`), `hiring_router` (prefix `/agents/hiring-assistant`), `career_router` (prefix `/agents`). Starts the Kafka consumer thread on startup via `threading.Thread(target=start_kafka_consumer, daemon=True).start()`.

### `ai-agents/config.py`
Environment configuration for the AI service. Notable settings:
- `GROQ_API_KEY` / `GROQ_BASE_URL` / `LLM_MODEL` — Groq API credentials and model name (default: `llama-3.3-70b-versatile`)
- `RESUME_PARSER_USE_LLM` — feature flag, default `false` (uses heuristic parser)
- `CAREER_COACH_USE_LLM` — feature flag, default `true`
- `KAFKA_INLINE_FALLBACK` — if `true`, runs hiring workflow directly when Kafka is unavailable
- `PROFILE_SERVICE_URL`, `JOB_SERVICE_URL`, `APPLICATION_SERVICE_URL` — all point to `http://platform-api:3000`

### `shared/service_client.py`
Async HTTP client for calling the platform-api from within the AI service:
- `get_member(member_id)` — fetches member profile via `POST /members/get`
- `get_job(job_id)` — fetches job details via `POST /jobs/get`
- `get_applications_by_job(job_id, limit)` — fetches applicants via `POST /applications/byJob`
- `search_members_by_keyword(keyword, limit)` — searches member pool by keyword (used as fallback when a job has no applicants)

All functions use `httpx.AsyncClient` with `raise_for_status()`.

### `shared/llm_client.py`
Thin wrapper around the Groq API (OpenAI-compatible endpoint):
- `has_llm()` — returns `True` if `GROQ_API_KEY` is set
- `chat_complete(messages, temperature, max_tokens, json_mode)` — sends a chat completion request. With `json_mode=True`, sets `response_format: {type: "json_object"}`. Default temperature 0.2 (near-deterministic). Timeout: 120 seconds.

### `shared/kafka_client.py`
- `get_producer()` — returns a singleton `KafkaProducer` with JSON value serializer
- `publish_event(topic, event_type, ...)` — wraps data in the standard event envelope and calls `producer.send(topic, value=envelope)`

### `shared/trace_store.py`
MongoDB persistence for AI task state using the `ai_tasks` collection:
- `persist_task(task)` — upserts the full `HiringTask` model (serialized to dict) keyed by `trace_id`
- `get_task_async(trace_id)` — retrieves and reconstructs a `HiringTask` from MongoDB
- `list_traces(limit)` — returns most recent traces (used by the evaluation summary endpoint)

The `HiringTask` Pydantic model (defined in `schemas.py`) carries: `trace_id`, `job_id`, `recruiter_id`, `status` (enum: pending/running/awaiting_approval/approved/completed/failed/cancelled/rejected), `step` (current step description), `shortlist` (list of scored candidates), `created_at`, `updated_at`.

### `shared/ai_prompts.py`
Prompt engineering for two LLM tasks:

**Hiring outreach:** System prompt instructs the LLM to act as a senior talent acquisition specialist and write professional LinkedIn InMail-style outreach. User payload includes job title, company, location, required skills, seniority, and candidate name/current role/skills/experience. Response must be JSON `{subject, body}`.

**Career coach:** System prompt instructs the LLM to act as a career advisor. User payload includes job title, required skills, candidate skills, years of experience, education, current headline, and resume excerpt. Response must be JSON `{headline_suggestion, resume_improvements[], skills_to_add[], cover_letter_tips[]}`.

### `agents/hiring_assistant/agent.py`
The core hiring workflow (supervisor agent pattern):

**`run_hiring_workflow(job_id, recruiter_id, top_k, trace_id)`** — async function:
1. Creates a `HiringTask` in MongoDB with `status=running`
2. Fetches job details; extracts required skills from `job_skills` table and job description using regex
3. Fetches applications for the job. If none, falls back to `search_members_by_keyword` using the top 3 job skills
4. For each application (up to 100), concurrently (semaphore=10):
   - Fetches member profile
   - Parses resume text (heuristic or LLM via `parse_resume`)
   - Scores against job using `compute_match` (skills overlap, location, experience band)
5. Sorts by score, takes top-K, generates outreach drafts using LLM (with heuristic fallback)
6. Sets `status=awaiting_approval`, persists shortlist to MongoDB, publishes `ai.result` to Kafka

**`handle_approval(trace_id, action, edited_outreach)`:**
- `approve` — marks task completed, records approval
- `edit` — saves edited outreach, marks completed
- `reject` — marks task rejected

**`get_evaluation_summary(limit)`** — aggregates metrics across recent tasks: total runs, completion rate, approval rate, average shortlist size, average match score.

Cancellation is checked at each async step via `_is_cancelled(trace_id)` which polls MongoDB.

### `agents/hiring_assistant/router.py`
REST + WebSocket interface:

- `POST /start` — validates recruiter + job, generates `trace_id`, either publishes to Kafka (`ai.requests` topic) or runs inline (if `KAFKA_INLINE_FALLBACK=true`), returns `{trace_id}`
- `POST /status` — reads current task state from MongoDB
- `POST /approve` — calls `handle_approval()`
- `POST /cancel` — sets task status to `cancelled` in MongoDB
- `GET /evaluation/summary` — returns aggregate metrics
- `WebSocket /ws/{trace_id}` — polls MongoDB every 0.5 seconds, sends task state JSON when it changes, closes when terminal status is reached (completed/approved/failed/etc.)

### `agents/hiring_assistant/schemas.py`
Pydantic models: `HiringTask`, `TaskStatus` enum, `CandidateScore` (member_id, match_score, explanation, skills_overlap, outreach_draft), `StartRequest`, `ApproveRequest`, `EvaluationSummaryResponse`.

### `skills/resume_parser/skill.py`
Two-mode resume parser:

**Heuristic mode (default):** regex extraction —
- Skills: matches against a 100+ keyword list (Python, SQL, React, Kafka, etc.)
- Experience: searches for patterns like "5 years", "3+ years"
- Education: looks for degree keywords (bachelor, master, PhD, BS, MS)
- Job titles: matches against seniority/role patterns

**LLM mode (`RESUME_PARSER_USE_LLM=true`):** sends resume text to Groq with a JSON schema prompt. Falls back to heuristic on failure.

Output: `{skills[], years_experience, education, job_titles[], summary}`.

### `skills/job_candidate_matcher/skill.py`
Deterministic scoring algorithm, no LLM:

**Score components (sum to 1.0):**
- Skills overlap (0–0.6): `matched_skills / max(job_skills_count, 1)` × 0.6. Applies skill aliases (e.g., "node" → "node.js", "ml" → "machine learning").
- Location match (0–0.2): 0.2 if city/state/country matches, 0.1 if country-only match.
- Experience band (0–0.2): compares candidate years to role's expected range by seniority. Penalizes overqualified candidates slightly (exceed by >3 years → 0.1 penalty).

Generates a plain-English explanation string for each score component.

### `agents/career_coach/router.py`
Single endpoint `POST /agents/career-coach`. Accepts:
- JSON body: `{member_id, job_id, resume_text?}`
- Multipart form: adds `resume_file` (PDF/DOC/DOCX)

Processing: extracts text from uploaded file (PDF: `pypdf2`, DOCX: `python-docx`), fetches member profile and job from platform-api, calls `run_career_coach()`, returns coaching suggestions.

### `agents/career_coach/coach_llm.py`
- `run_career_coach_llm(member, job, resume_text, parsed_resume)` — builds prompt using `ai_prompts.career_coach_*` functions, calls `chat_complete()` with JSON mode, parses response
- `merge_with_heuristic(llm_output, member, job, parsed_resume)` — ensures minimum content by supplementing LLM output with heuristic suggestions (skill gap analysis, generic resume tips)
- Output schema: `{headline_suggestion, resume_improvements[], skills_to_add[], cover_letter_tips[]}`

### `app_kafka/consumer.py`
Kafka consumer for the `ai.requests` topic (group: `ai-agent-group`). Listens for events with `event_type=ai.requested`, extracts `job_id`, `recruiter_id`, `top_k` from payload, dispatches `run_hiring_workflow()`. If the async event loop is running (uvicorn thread), submits as a coroutine; otherwise runs in a new loop. Runs indefinitely as a daemon thread.

---

## `client/` — React Frontend

A single-page React application served by Nginx. The build output in `client/build/` is served as static files. Nginx proxies `/api/` to `platform-api:3000` and `/ws/` to `ai-agent-service:8000`.

### `client/Dockerfile`
Multi-stage build:
1. **Stage 1 (node:20-alpine):** `npm install` then `npm run build` — compiles React to `build/`
2. **Stage 2 (nginx:alpine):** Copies `build/` to `/usr/share/nginx/html`, copies `nginx.conf`, exposes port 80

### `client/nginx.conf`
Three location blocks:
- `/` — serves static files, falls back to `index.html` (React Router SPA mode)
- `/api/` — proxies to `http://platform-api:3000` with `Host` and `X-Real-IP` headers
- `/ws/` — WebSocket proxy to `http://ai-agent-service:8000` with HTTP/1.1 upgrade headers, 300-second read timeout

### `client/src/index.js`
React app entry point. Wraps `<App>` in `<BrowserRouter>` from `react-router-dom`.

### `client/src/App.js`
Top-level component. Manages:
- Authentication state via `localStorage` (`member_id`, `recruiter_id`, `user_name`, `role`, `token`)
- Session validation on mount (calls `/members/get` or `/recruiters/get`; logs out if user no longer exists — handles post-reseed stale sessions)
- Navigation bar with LinkedIn-style icons, active route highlighting, profile dropdown
- Nav search bar: on Enter, navigates to `/connections?tab=find&q=<query>`
- Role-based routing: members see Home/Network/Jobs/Messaging/Analytics/AI; recruiters see Home/Dashboard/Network/Messaging/AI
- `<Routes>` defining all page paths

### `client/src/api/apiClient.js`
Axios instance with `baseURL: '/api'`. Request interceptor attaches `Authorization: Bearer <token>` and `x-member-id` headers from `localStorage` on every request. Also exports `uuid()` — a Math.random-based UUID v4 generator (works on plain HTTP, unlike `crypto.randomUUID()` which requires HTTPS).

### `client/src/api/aiApi.js`
- `startHiringAssistant(data)` → `POST /agents/hiring-assistant/start`
- `getHiringStatus(trace_id)` → `POST /agents/hiring-assistant/status`
- `approveHiring(data)` → `POST /agents/hiring-assistant/approve`
- `careerCoach(data)` → `POST /agents/career-coach` (handles both JSON and FormData)
- `parseResume(data)` → `POST /skills/parse-resume`
- `hiringWsUrl(trace_id)` — constructs WebSocket URL using `window.location.protocol` and `window.location.host` (same-origin, no hardcoded port)

### `client/src/api/analyticsApi.js`
Functions: `getAnalyticsOverview`, `getTopJobs`, `getActiveMembers`, `getRecruiterDashboard`, `getFunnel`, `getGeo`, `getAiMetrics` — all POSTs to `/analytics/*`.

### `client/src/api/applicationApi.js`
`submitApplication(data)` → `POST /applications/submit`. `applicationsByMember(member_id)` → `POST /applications/byMember`. `applicationsByJob(data)` → `POST /applications/byJob`. `updateApplicationStatus(data)` → `POST /applications/updateStatus`.

### `client/src/api/connectionApi.js`
`sendRequest`, `acceptRequest`, `rejectRequest`, `listConnections`, `mutualConnections`, `pendingRequests`, `sentRequests` — all thin wrappers around the connections API endpoints.

### `client/src/api/jobApi.js`
`searchJobs`, `getJob`, `createJob`, `closeJob`, `savedJobs`, `saveJob`, `unsaveJob`, `jobsByRecruiter` — all wrappers for job endpoints.

### `client/src/api/messagingApi.js`
`openThread`, `getThread`, `threadsByUser`, `sendMessage`, `listMessages`. `sendMessage` includes an `idempotency_key: uuid()` to prevent duplicate messages on network retry.

### `client/src/api/postApi.js`
`getFeedPosts`, `getSavedPosts`, `createPost`, `likePost`, `unlikePost`, `savePost`, `unsavePost`, `addPostComment`, `deletePostComment`.

### `client/src/api/profileApi.js`
`getMember`, `updateMember`, `addSkill`, `removeSkill`, `getRecruiter`.

---

## Page Components

### `pages/LoginPage.jsx`
Dual-mode login form (Member / Recruiter toggle). On submit, POSTs to `/members/login` or `/recruiters/login`, stores `token`, `member_id`/`recruiter_id`, `user_name`, `role` in `localStorage`, calls `onLogin(userData)` prop to update App state. Has a registration form that POSTs to `/members/create` or `/recruiters/create`.

### `pages/HomeFeedPage.jsx`
LinkedIn-style home feed. Loads posts from `/posts/` on mount. Supports infinite scroll (loads more on button click). `PostCard` component handles like/unlike (optimistic UI update), save/unsave, add/delete comments with inline form. Sidebar shows quick links and news headlines. Saved posts accessible via `/home/saved` route.

### `pages/JobsPage.jsx`
Exports two components:

**`JobsPage`** — compact job widget for the sidebar. Shows saved/recommended jobs, links to the browse page.

**`JobsBrowsePage`** — full job search interface with:
- Keyword, location, and seniority filters plus filter pills (employment type, work mode)
- Paginated results (20 per page) with "Load more (N remaining)" button
- `totalJobs` state from API `total` field; displays "X of Y jobs"
- Job detail panel on the right (selected job)
- Apply modal with idempotency key (prevents duplicate applications)
- Save/unsave toggle with optimistic UI

### `pages/ProfilePage.jsx`
Member profile view and edit. Fetches own profile via `getMember`. Supports: headline and about editing, profile photo upload (resized client-side to JPEG via `imageResize.js`, stored as base64 data URL), skill add/remove. Shows connection count and profile views. Can also view other members' profiles via `?member_id=` query param (read-only mode for others).

### `pages/ConnectionsPage.jsx`
Four tabs:
- **My Connections** — grid of accepted connections with "View Profile" links
- **Find People** — search input + results grid with Connect/Pending/Connected states. Reads `?tab=find&q=<query>` URL params (set by nav search bar), auto-searches on load. Error handling extracts nested `detail.error` objects from 409 responses.
- **Pending Requests** — incoming requests with Accept/Decline buttons
- **Sent Requests** — outgoing pending requests

Connect button sends `POST /connections/request` with `idempotency_key`.

### `pages/MessagesPage.jsx`
Full messaging UI with:
- Left sidebar: thread list with unread indicators (based on `last_seen` stored in `localStorage`)
- Thread filters: Focused, Unread, Connections, All
- Thread search
- New message modal: searches members and recruiters, opens or creates a thread
- Right info rail: participant details, mutual connections (desktop)
- `sendMessage` uses `sendMessageApi` from `messagingApi.js` (includes `idempotency_key`). On failure: restores text in input, shows error toast
- Toast system: `showToast(msg, type)` renders a fixed-position overlay that auto-dismisses in 4 seconds

### `pages/RecruiterPage.jsx`
Full recruiter dashboard with five tabs:

**Analytics** — charts using Recharts: top jobs by application count (bar chart from analytics backend `top_jobs_by_applications`), application trend over time, city-wise heatmap, low-traction jobs list, AI agent metrics.

**My Jobs** — table of recruiter's job postings with open/closed status, applicant count, view count. Can close a job.

**Talent Pipeline** — applicant list for selected job with status update controls (move through hiring funnel), application funnel chart, geographic breakdown.

**Find Candidates** — search members by keyword/skill/location, view profiles, initiate messaging.

**Post Job** — form to create a new job posting with all fields.

### `pages/AIAssistantPage.jsx`
Two sub-tools (tab-based):

**Hiring Assistant (recruiters only):**
- Select job from dropdown, set Top K
- `startAssistant()` POSTs to start endpoint, gets `trace_id`
- `connectWebSocket(tid)` opens WS to `/ws/agents/hiring-assistant/ws/{trace_id}`. Uses `settled` flag to prevent double-polling: if WS receives a terminal status, `settled=true`; `onclose` only starts polling if `!settled`; `onerror` only starts polling if `!settled`
- Falls back to `pollStatus()` (polls every 3 seconds, up to 20 times) if WS unavailable
- `CandidateCard` shows match score, skill overlap, editable outreach draft, approve/edit/reject buttons

**Career Coach (members only):**
- Select target job from dropdown (loaded from job search, deduplicated and diversified across role categories)
- Optional resume file upload (PDF/DOC/DOCX) or text paste
- Submits to `POST /agents/career-coach`
- Displays suggestions: headline, resume improvements, skills to add, cover letter tips

### `pages/AnalyticsDashboard.jsx`
Member-facing analytics with Recharts visualizations: job application trends, top companies hiring, skill demand, geographic distribution of jobs. Data pulled from analytics API endpoints.

### `pages/RecruiterProfileViewPage.jsx`
Read-only view of a recruiter profile. Accessed at `/recruiter/profile?recruiter_id=`. Shows company info, industry, hiring highlights.

### `pages/CareerResourcesPage.jsx`
Static informational page with three cards: Resume Improvement Checklist, Interview Prep Plan, Networking Playbook.

### `pages/LoginPage.jsx`
Already described above.

### `utils/imageResize.js`
`resizeImageToJpegDataUrl(file, maxWidth=800, maxHeight=800, quality=0.85)` — draws image on a canvas element, downscales if needed, exports as JPEG data URL. Used before uploading profile photos to keep payload size reasonable.

---

## Database Layer

### `databases/mysql/init/` — MySQL Schema

All scripts run in order on first container startup (MySQL Docker convention).

**`00_create_databases.sql`** — Creates `linkedin_ds` database.

**`01_profiles.sql`** — `members` table: `member_id` (UUID PK), `first_name`, `last_name`, `email` (UNIQUE), `password_hash`, `headline`, `about`, `city`, `state`, `country`, `resume_text`, `profile_photo_url`, `connections_count`, `profile_views_count`, `is_deleted`. Also `member_skills(member_id, skill)` — many-to-many skills. Also `recruiters` table with company fields.

**`02_jobs.sql`** — `jobs` table: `job_id`, `recruiter_id` (FK), `company_id`, `title`, `description`, `seniority_level`, `employment_type`, `work_mode`, `city/state/country`, `salary_min/max`, `industry`, `status` (open/closed), `views_count`, `saves_count`, `applicants_count`, `posted_at`. Also `job_skills(job_id, skill)`.

**`03_applications.sql`** — `applications` table: `application_id`, `job_id` (FK), `member_id` (FK), `resume_url`, `resume_text`, `cover_letter`, `answers`, `status` (submitted/reviewing/interview/offer/rejected), `idempotency_key` (UNIQUE). Also `application_notes` and `application_status_history` audit tables.

**`04_connections.sql`** — `connection_requests(request_id, requester_id, receiver_id, message, status, idempotency_key)`. `connections(id, member_a, member_b, connected_at)` — normalized pair (member_a < member_b lexicographically via `normalize_pair`).

**`05_posts.sql`** through **`09_profile_photos.sql`** — posts, likes, comments, saved posts, and profile photos tables.

### `databases/mongodb/init/`

**`01_messages.js`** — Creates `threads` and `messages` collections with indexes: `threads.participant_ids`, `threads.updated_at`; `messages.thread_id`, `messages.sent_at`, `messages.idempotency_key` (unique).

**`02_analytics.js`** — Creates `event_logs` collection with indexes on `event_type`, `timestamp`, `actor_id`, `payload.job_id`, `payload.recruiter_id` for efficient analytics aggregations. Also creates `ai_tasks` collection with index on `trace_id`.

### `databases/seed.py`
Full Python seeder script (~900 lines). Run manually: `python3 databases/seed.py` (full) or `python3 databases/seed.py --fast` (smaller dataset).

**What it seeds:**
- 10 fixed "demo" recruiters with real company names (Google, Meta, Apple, etc.)
- Up to 10,000 members with realistic names, headlines, skills, locations
- Up to 10,000 jobs (80% open, 20% closed) with salary ranges, skills, locations
- Applications linking members to jobs
- Connection requests between members
- Posts with realistic content

**How it works:**
- Uses `pymysql` (synchronous) for MySQL and `pymongo` for MongoDB
- Auto-installs missing pip packages via `subprocess.check_call`
- `--keep` flag skips truncation (preserves existing data)
- Reads from CSV datasets in `datasets/` for names, companies, job titles, locations
- Writes benchmark helper files to `databases/benchmarks/` (application pairs CSV for JMeter load tests)

---

## Kafka Configuration

### `kafka/config/topics.json`
Documents 15 Kafka topics, their partition counts, replication factors, and the producer→consumer relationships for each:

| Topic | Producer | Consumer(s) |
|---|---|---|
| `profile.created` | members router | analytics |
| `profile.updated` | members router | analytics |
| `profile.viewed` | members router | analytics |
| `job.posted` | jobs router | analytics |
| `job.viewed` | jobs router | analytics |
| `job.saved` | jobs router | analytics |
| `job.closed` | jobs router | analytics, application consumer |
| `application.submitted` | applications router | analytics, ai-agent-service |
| `application.status.changed` | applications router | analytics |
| `message.sent` | messaging router | analytics |
| `connection.requested` | connections router | analytics |
| `connection.accepted` | connections router | analytics, connection consumer |
| `connection.rejected` | connections router | analytics |
| `ai.requests` | hiring assistant router | ai-agent-service kafka consumer |
| `ai.result` | hiring assistant agent | analytics |

### `kafka/scripts/create-topics.sh`
Shell script run as a one-shot Docker container on startup. Sleeps 10 seconds for Kafka readiness, then calls `kafka-topics.sh --create` for each of the 15 topics with `--partitions 3 --replication-factor 1`.

---

## Infrastructure

### `redis/redis.conf`
Minimal Redis configuration: sets `maxmemory-policy allkeys-lru` (evicts least recently used keys when memory is full — appropriate for a cache). Default port 6379.

### `docker-compose.yml` (detailed)
**Service dependency chain:**
```
zookeeper → kafka → [platform-api, ai-agent-service]
mysql, mongodb, redis → platform-api
platform-api → client (nginx)
```

All services use `restart: unless-stopped`. Health checks use `CMD-SHELL` with the actual service-specific check command. Platform-api and ai-agent-service both get `GROQ_API_KEY` from the environment.

### `infrastructure/k8s/linkedin-stack.yaml`
Kubernetes manifests for deploying the full stack as Deployments and Services on a K8s cluster. Each service has a corresponding `Deployment` + `Service`. Uses `ConfigMap` for environment variables and `PersistentVolumeClaim` for MySQL/MongoDB data.

### `infrastructure/scripts/setup.sh`
Bash script for EC2 provisioning: installs Docker, Docker Compose plugin, creates project directory, sets up `.env` from template.

### `infrastructure/benchmarks/`
JMeter load test result CSV files and Python scripts that parse them to generate performance comparison charts. Four scenarios tested: B (baseline), B+S (with Redis cache), B+S+K (cache + Kafka), B+S+K+O (full stack + other services). Charts saved to `charts/` as PNG files used in the project report.

### `performance/benchmarks/benchmark_api.py`
Async Python benchmark script using `httpx`. Sends concurrent requests to key endpoints (job search, job detail, application submit) and records latency percentiles (P50, P95, P99) and throughput. Configurable concurrency level and request count.

---

## Documentation

### `docs/api-document.md`
Complete REST API reference: every endpoint with request body schema, response schema, and example payloads.

### `docs/kafka-topics.md`
Describes each Kafka topic's purpose, event envelope format, and the data flow between producers and consumers.

### `docs/diagrams/system-architecture.md`
System architecture diagram in Mermaid format showing all containers, their connections, and external integrations.

### `docs/diagrams/database-schema.md`
Entity-relationship diagram of the MySQL schema and MongoDB collection structure.

### `docs/diagrams/agent-architecture.md`
Agent flow diagram showing the hiring assistant's supervisor pattern: start → Kafka → consumer → workflow → shortlist → approval → completion.

---

## Key Design Decisions

**Single platform-api instead of microservices:** The original design had 7 Node.js microservices (api-gateway, profile-service, job-service, etc.). These were consolidated into one Python FastAPI service to eliminate Node.js entirely and simplify deployment. The router-per-domain pattern preserves logical separation.

**Redis caching at TTL=300s:** Member profiles are cached because they are read-heavy (profile views, connection resolution, feed rendering) and update infrequently. Cache is invalidated on update and deleted-member operations.

**MongoDB for events and messages:** Event logs are append-only and schema-flexible (each event type has a different payload shape). MongoDB's document model and aggregation pipeline handle this better than MySQL. Messages are also document-oriented with variable content.

**MySQL for transactional data:** Applications, connections, and job postings require ACID transactions (e.g., preventing duplicate applications via `UNIQUE(job_id, member_id)`, atomically incrementing `applicants_count`).

**Kafka for event-driven side effects:** Job closure automatically rejects open applications (application consumer). Connections automatically increment counters on both profiles (connection consumer). Analytics are populated asynchronously by the analytics consumer without blocking API responses.

**Heuristic-first AI:** Resume parsing uses regex by default (`RESUME_PARSER_USE_LLM=false`) to keep inference costs low. The job-candidate matcher is entirely deterministic (no LLM). The LLM is only called for subjective tasks: generating outreach drafts and career coaching suggestions.

**WebSocket with polling fallback:** The hiring assistant result can take 10–60 seconds. WebSocket (`/ws/agents/hiring-assistant/ws/{trace_id}`) pushes updates in real time. If the WS handshake fails (plain HTTP environments), the client polls `getHiringStatus` every 3 seconds for up to 60 seconds. A `settled` local flag prevents double-polling when WS succeeds but then closes.
