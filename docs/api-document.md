# LinkedIn-Like Distributed System — API Design Document

**Course:** Distributed Systems  
**Due Date:** April 7, 2026  
**Version:** 1.0

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Service Architecture](#2-service-architecture)
3. [Standard Conventions](#3-standard-conventions)
4. [Kafka Event Envelope](#4-kafka-event-envelope)
5. [Profile Service](#5-profile-service)
6. [Job Service](#6-job-service)
7. [Application Service](#7-application-service)
8. [Messaging Service](#8-messaging-service)
9. [Connection Service](#9-connection-service)
10. [Analytics / Logging Service](#10-analytics--logging-service)
11. [AI Agent Service (FastAPI)](#11-ai-agent-service-fastapi)
12. [Kafka Topics Reference](#12-kafka-topics-reference)
13. [Error Codes](#13-error-codes)
14. [Database Justification](#14-database-justification)

---

## 1. System Overview

This system implements a LinkedIn-like professional networking and hiring platform using a 3-tier, service-oriented architecture:

- **Tier 1 — Client:** React web UI (member + recruiter modules)
- **Tier 2 — Services + Kafka:** Six REST microservices (Node.js/Express) + one AI service (FastAPI), communicating asynchronously via Apache Kafka
- **Tier 3 — Databases:** MySQL (transactional data) + MongoDB (logs, unstructured data, agent traces)

**API Gateway** (port 3000) is the single entry point. All client requests go through it; it forwards to backend services via reverse proxy.

---

## 2. Service Architecture

| Service | Port | Database | Kafka Role |
|---------|------|----------|------------|
| API Gateway | 3000 | Redis (JWT cache) | — |
| Profile Service | 3001 | MySQL | Producer |
| Job Service | 3002 | MySQL | Producer |
| Application Service | 3003 | MySQL | Producer + Consumer |
| Messaging Service | 3004 | MongoDB | Producer |
| Connection Service | 3005 | MySQL | Producer |
| Analytics Service | 3006 | MongoDB | Consumer (all topics) |
| AI Agent Service | 8000 | MongoDB | Producer + Consumer |

---

## 3. Standard Conventions

### Base URL
All requests go through the API Gateway:
```
http://<host>:3000/api
```

### HTTP Method
All service endpoints use **POST** with a JSON body (as specified in the project requirements).

### Authentication
```
Authorization: Bearer <JWT token>
```
JWT is validated at the API Gateway. The `member_id` or `recruiter_id` is injected as `x-user-id` header to downstream services.

### Public Endpoints (no JWT required)
- `POST /members/create`
- `POST /recruiters/create`

### Response Envelope

**Success:**
```json
{ "field": "value", ... }
```

**Error:**
```json
{
  "error": "Human-readable error message"
}
```

### Pagination (where applicable)
Request: `"page": 1, "limit": 20`  
Response: `{ "results": [...], "page": 1, "limit": 20 }`

---

## 4. Kafka Event Envelope

All Kafka messages across all topics use this shared JSON envelope:

```json
{
  "event_type":      "job.viewed",
  "trace_id":        "550e8400-e29b-41d4-a716-446655440000",
  "timestamp":       "2026-04-07T10:30:00.000Z",
  "actor_id":        "member_id or recruiter_id",
  "entity": {
    "entity_type":   "job | application | thread | connection | member | ai_task",
    "entity_id":     "uuid"
  },
  "payload": {
    "domain_specific_fields": "..."
  },
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440001"
}
```

**Rules:**
- `trace_id` stays the same across a multi-step workflow (UI → Kafka → service → AI)
- `idempotency_key` is checked by consumers before every DB write to prevent duplicates
- `event_type` matches the Kafka topic name

---

## 5. Profile Service

**Base path:** `/members` and `/recruiters`

---

### 5.1 Create Member

`POST /members/create`

**Request:**
```json
{
  "first_name":  "Jane",
  "last_name":   "Smith",
  "email":       "jane@example.com",
  "phone":       "+1-555-0100",
  "city":        "San Francisco",
  "state":       "CA",
  "country":     "USA",
  "headline":    "Software Engineer at Google",
  "about":       "Passionate about distributed systems..."
}
```

**Required fields:** `first_name`, `last_name`, `email`

**Response `201`:**
```json
{ "member_id": "uuid" }
```

**Error `409`:** Email already registered  
**Kafka:** Publishes to `profile.updated` (`event_type: profile.created`)

---

### 5.2 Get Member Profile

`POST /members/get`

**Request:**
```json
{ "member_id": "uuid" }
```

**Response `200`:**
```json
{
  "member_id":        "uuid",
  "first_name":       "Jane",
  "last_name":        "Smith",
  "email":            "jane@example.com",
  "phone":            "+1-555-0100",
  "city":             "San Francisco",
  "state":            "CA",
  "country":          "USA",
  "headline":         "Software Engineer at Google",
  "about":            "...",
  "profile_photo_url": "https://...",
  "resume_url":       "https://...",
  "connections_count": 142,
  "skills":           ["Python", "Kafka", "Docker"],
  "created_at":       "2026-03-01T00:00:00Z",
  "_cache":           false
}
```

`_cache: true` indicates the response was served from Redis.

---

### 5.3 Update Member Profile

`POST /members/update`

**Request:**
```json
{
  "member_id": "uuid",
  "headline":  "Senior Engineer",
  "about":     "Updated summary...",
  "city":      "Seattle"
}
```

**Updatable fields:** `first_name`, `last_name`, `phone`, `city`, `state`, `country`, `headline`, `about`, `profile_photo_url`, `resume_url`

**Response `200`:**
```json
{ "success": true }
```

**Side effect:** Invalidates Redis cache for `member:{member_id}`  
**Kafka:** Publishes to `profile.updated`

---

### 5.4 Delete Member

`POST /members/delete`

**Request:**
```json
{ "member_id": "uuid" }
```

**Response `200`:**
```json
{ "success": true }
```

---

### 5.5 Search Members

`POST /members/search`

**Request:**
```json
{
  "skill":    "Python",
  "location": "San Francisco",
  "keyword":  "engineer",
  "page":     1,
  "limit":    20
}
```

**Response `200`:**
```json
{
  "results": [ { ...member objects... } ],
  "page":    1,
  "limit":   20
}
```

---

### 5.6 Create Recruiter

`POST /recruiters/create`

**Request:**
```json
{
  "first_name":        "Bob",
  "last_name":         "Jones",
  "email":             "bob@techcorp.com",
  "phone":             "+1-555-0200",
  "company_id":        "uuid (optional, auto-generated if omitted)",
  "company_name":      "TechCorp Inc.",
  "company_industry":  "Technology",
  "company_size":      "1001-5000",
  "role":              "recruiter"
}
```

**Response `201`:**
```json
{ "recruiter_id": "uuid", "company_id": "uuid" }
```

---

### 5.7 Get Recruiter

`POST /recruiters/get`

**Request:**
```json
{ "recruiter_id": "uuid" }
```

**Response `200`:** Full recruiter object

---

## 6. Job Service

**Base path:** `/jobs`

---

### 6.1 Create Job

`POST /jobs/create`

**Request:**
```json
{
  "company_id":       "uuid",
  "recruiter_id":     "uuid",
  "title":            "Senior Software Engineer",
  "description":      "We are looking for...",
  "seniority_level":  "Mid-Senior level",
  "employment_type":  "Full-time",
  "city":             "Austin",
  "state":            "TX",
  "country":          "USA",
  "work_mode":        "hybrid",
  "salary_min":       120000,
  "salary_max":       160000,
  "industry":         "Technology",
  "skills":           ["Python", "Kafka", "AWS"]
}
```

**Required:** `recruiter_id`, `title`

**`seniority_level` values:** `Internship` | `Entry level` | `Associate` | `Mid-Senior level` | `Director` | `Executive`  
**`employment_type` values:** `Full-time` | `Part-time` | `Contract` | `Temporary` | `Internship`  
**`work_mode` values:** `onsite` | `remote` | `hybrid`

**Response `201`:**
```json
{ "job_id": "uuid" }
```

**Kafka:** Publishes to `job.posted`

---

### 6.2 Get Job

`POST /jobs/get`

**Request:**
```json
{ "job_id": "uuid" }
```

**Response `200`:**
```json
{
  "job_id":           "uuid",
  "company_id":       "uuid",
  "recruiter_id":     "uuid",
  "title":            "Senior Software Engineer",
  "description":      "...",
  "seniority_level":  "Mid-Senior level",
  "employment_type":  "Full-time",
  "city":             "Austin",
  "state":            "TX",
  "country":          "USA",
  "work_mode":        "hybrid",
  "salary_min":       120000,
  "salary_max":       160000,
  "industry":         "Technology",
  "status":           "open",
  "views_count":      452,
  "applicants_count": 37,
  "saves_count":      18,
  "skills":           ["Python", "Kafka", "AWS"],
  "posted_at":        "2026-04-01T09:00:00Z",
  "_cache":           true
}
```

**Side effect:** Increments `views_count`; publishes `job.viewed` to Kafka

---

### 6.3 Update Job

`POST /jobs/update`

**Request:**
```json
{
  "job_id":      "uuid",
  "title":       "Principal Software Engineer",
  "salary_max":  180000,
  "work_mode":   "remote"
}
```

**Response `200`:**
```json
{ "success": true }
```

---

### 6.4 Search Jobs

`POST /jobs/search`

**Request:**
```json
{
  "keyword":         "machine learning",
  "location":        "New York",
  "employment_type": "Full-time",
  "industry":        "Technology",
  "work_mode":       "remote",
  "page":            1,
  "limit":           20
}
```

All fields optional. Uses MySQL `LIKE` pattern matching on `title` + `description`.

**Response `200`:**
```json
{
  "results": [ { ...job objects... } ],
  "page":    1,
  "limit":   20
}
```

---

### 6.5 Close Job

`POST /jobs/close`

**Request:**
```json
{
  "job_id":       "uuid",
  "recruiter_id": "uuid"
}
```

**Response `200`:**
```json
{ "success": true }
```

**Side effect:** Sets `status = "closed"`, `closed_at = NOW()`  
**Kafka:** Publishes `job.closed` → consumed by Application Service to reject pending applications

---

### 6.6 List Jobs by Recruiter

`POST /jobs/byRecruiter`

**Request:**
```json
{ "recruiter_id": "uuid", "page": 1, "limit": 20 }
```

**Response `200`:**
```json
{
  "results": [ { ...job objects... } ],
  "page":    1,
  "limit":   20
}
```

---

## 7. Application Service

**Base path:** `/applications`

---

### 7.1 Submit Application

`POST /applications/submit`

**Request:**
```json
{
  "job_id":           "uuid",
  "member_id":        "uuid",
  "resume_url":       "https://storage/resume.pdf",
  "resume_text":      "Extracted text from resume...",
  "cover_letter":     "Dear Hiring Manager...",
  "idempotency_key":  "client-generated-uuid"
}
```

**Required:** `job_id`, `member_id`

**Response `201`:**
```json
{ "application_id": "uuid" }
```

**Error `409` — Duplicate application:** `{ "error": "Already applied to this job" }`  
**Error `409` — Job closed:** `{ "error": "Cannot apply to a closed job" }`  
**Kafka:** Publishes to `application.submitted`  
**Transaction:** Checks job status + inserts application + increments `applicants_count` atomically

---

### 7.2 Get Application

`POST /applications/get`

**Request:**
```json
{ "application_id": "uuid" }
```

**Response `200`:**
```json
{
  "application_id":  "uuid",
  "job_id":          "uuid",
  "member_id":       "uuid",
  "resume_url":      "https://...",
  "cover_letter":    "...",
  "status":          "reviewing",
  "applied_at":      "2026-04-02T14:00:00Z",
  "updated_at":      "2026-04-03T09:00:00Z"
}
```

---

### 7.3 List Applications by Job (Recruiter View)

`POST /applications/byJob`

**Request:**
```json
{ "job_id": "uuid", "page": 1, "limit": 20 }
```

**Response `200`:**
```json
{
  "results": [ { ...application objects... } ],
  "page":    1,
  "limit":   20
}
```

---

### 7.4 List Applications by Member

`POST /applications/byMember`

**Request:**
```json
{ "member_id": "uuid", "page": 1, "limit": 20 }
```

**Response `200`:** Same structure as 7.3

---

### 7.5 Update Application Status

`POST /applications/updateStatus`

**Request:**
```json
{
  "application_id": "uuid",
  "status":         "interview",
  "recruiter_id":   "uuid"
}
```

**`status` values:** `submitted` → `reviewing` → `interview` → `offer` | `rejected`

**Response `200`:**
```json
{ "success": true }
```

**Side effect:** Writes status change to `application_status_history`  
**Kafka:** Publishes to `application.status.changed`

---

### 7.6 Add Recruiter Note

`POST /applications/addNote`

**Request:**
```json
{
  "application_id": "uuid",
  "recruiter_id":   "uuid",
  "note":           "Strong candidate. Schedule for technical interview."
}
```

**Response `201`:**
```json
{ "success": true }
```

---

## 8. Messaging Service

**Base paths:** `/threads`, `/messages`

---

### 8.1 Open Thread

`POST /threads/open`

**Request:**
```json
{
  "participant_ids": ["member-uuid-1", "recruiter-uuid-2"]
}
```

**Response `201`:**
```json
{ "thread_id": "uuid" }
```

---

### 8.2 Get Thread

`POST /threads/get`

**Request:**
```json
{ "thread_id": "uuid" }
```

**Response `200`:**
```json
{
  "thread_id":       "uuid",
  "participant_ids": ["uuid1", "uuid2"],
  "last_message":    "Looking forward to speaking with you!",
  "updated_at":      "2026-04-06T10:00:00Z",
  "created_at":      "2026-04-01T08:00:00Z"
}
```

---

### 8.3 List Threads by User

`POST /threads/byUser`

**Request:**
```json
{ "user_id": "uuid", "page": 1, "limit": 20 }
```

**Response `200`:**
```json
{
  "results": [ { ...thread objects... } ],
  "page":    1,
  "limit":   20
}
```

---

### 8.4 Send Message

`POST /messages/send`

**Request:**
```json
{
  "thread_id":       "uuid",
  "sender_id":       "uuid",
  "message_text":    "Hi! I saw your application...",
  "idempotency_key": "client-generated-uuid"
}
```

**Response `201`:**
```json
{ "message_id": "uuid" }
```

**Error `409`:** Duplicate message (idempotency key reused)  
**Kafka:** Publishes to `message.sent`

---

### 8.5 List Messages in Thread

`POST /messages/list`

**Request:**
```json
{ "thread_id": "uuid", "page": 1, "limit": 50 }
```

**Response `200`:**
```json
{
  "results": [
    {
      "message_id":   "uuid",
      "thread_id":    "uuid",
      "sender_id":    "uuid",
      "message_text": "Hello!",
      "sent_at":      "2026-04-05T15:30:00Z"
    }
  ],
  "page":  1,
  "limit": 50
}
```

---

## 9. Connection Service

**Base path:** `/connections`

---

### 9.1 Send Connection Request

`POST /connections/request`

**Request:**
```json
{
  "requester_id":    "uuid",
  "receiver_id":     "uuid",
  "message":         "Hi! We met at the conference.",
  "idempotency_key": "client-generated-uuid"
}
```

**Response `201`:**
```json
{ "request_id": "uuid" }
```

**Error `409`:** Request already exists  
**Kafka:** Publishes to `connection.requested`

---

### 9.2 Accept Connection

`POST /connections/accept`

**Request:**
```json
{ "request_id": "uuid" }
```

**Response `200`:**
```json
{ "success": true }
```

**Side effect (transactional):**
1. Updates `connection_requests.status = "accepted"`
2. Inserts into `connections` (bidirectional)
3. Increments `connections_count` for both members  

**Kafka:** Publishes to `connection.accepted`

---

### 9.3 Reject Connection

`POST /connections/reject`

**Request:**
```json
{ "request_id": "uuid" }
```

**Response `200`:**
```json
{ "success": true }
```

---

### 9.4 List Connections

`POST /connections/list`

**Request:**
```json
{ "user_id": "uuid", "page": 1, "limit": 20 }
```

**Response `200`:**
```json
{
  "results": [ { ...member objects... } ],
  "page":    1,
  "limit":   20
}
```

---

### 9.5 Mutual Connections (Extra Credit)

`POST /connections/mutual`

**Request:**
```json
{ "user_id": "uuid", "other_id": "uuid" }
```

**Response `200`:**
```json
{
  "results": [ { ...member objects who are connected to both... } ]
}
```

---

## 10. Analytics / Logging Service

**Base paths:** `/events`, `/analytics`

---

### 10.1 Ingest Event

`POST /events/ingest`

For manual UI-side event tracking (page views, button clicks, etc.)

**Request:**
```json
{
  "event_type":      "profile.viewed",
  "actor_id":        "uuid",
  "entity": {
    "entity_type":   "member",
    "entity_id":     "uuid"
  },
  "payload": {
    "source": "search_results"
  },
  "idempotency_key": "uuid"
}
```

**Response `201`:**
```json
{ "success": true }
```

---

### 10.2 Top Jobs by Metric

`POST /analytics/jobs/top`

**Request:**
```json
{
  "metric":      "applications",
  "window_days": 30,
  "limit":       10
}
```

**`metric` values:** `applications` | `views` | `saves`

**Response `200`:**
```json
{
  "metric":      "applications",
  "window_days": 30,
  "results": [
    { "job_id": "uuid", "count": 142 },
    { "job_id": "uuid", "count": 98 }
  ]
}
```

---

### 10.3 Application Funnel

`POST /analytics/funnel`

**Request:**
```json
{ "job_id": "uuid", "window_days": 30 }
```

**Response `200`:**
```json
{
  "job_id":      "uuid",
  "window_days": 30,
  "funnel": {
    "views":        452,
    "saves":        38,
    "applications": 21
  }
}
```

---

### 10.4 Geo Distribution

`POST /analytics/geo`

**Request:**
```json
{ "job_id": "uuid", "window_days": 30 }
```

**Response `200`:**
```json
{
  "job_id":      "uuid",
  "window_days": 30,
  "geo": [
    { "_id": "San Francisco, CA", "count": 8 },
    { "_id": "New York, NY",      "count": 5 }
  ]
}
```

---

### 10.5 Member Dashboard

`POST /analytics/member/dashboard`

**Request:**
```json
{ "member_id": "uuid", "window_days": 30 }
```

**Response `200`:**
```json
{
  "member_id":   "uuid",
  "window_days": 30,
  "profile_views": [
    { "_id": "2026-04-01", "views": 12 },
    { "_id": "2026-04-02", "views": 8 }
  ],
  "application_status_breakdown": [
    { "_id": "submitted",  "count": 3 },
    { "_id": "reviewing",  "count": 2 },
    { "_id": "interview",  "count": 1 },
    { "_id": "rejected",   "count": 1 }
  ]
}
```

---

## 11. AI Agent Service (FastAPI)

**Base URL:** `http://<host>:8000`  
All AI endpoints are also accessible via the API Gateway at `/api/agents` and `/api/skills`.

---

### 11.1 Parse Resume

`POST /skills/parse-resume`

**Request:**
```json
{
  "resume_text": "John Doe — Software Engineer\n5 years experience in Python...",
  "member_id":   "uuid (optional)"
}
```

**Response `200`:**
```json
{
  "skills":           ["Python", "Kafka", "Docker", "AWS"],
  "years_experience": 5.0,
  "education": [
    { "degree": "BS", "field": "Computer Science", "school": "MIT", "year": 2019 }
  ],
  "job_titles":  ["Software Engineer", "Backend Developer"],
  "summary":     "Experienced backend engineer specializing in distributed systems"
}
```

---

### 11.2 Match Candidate to Job

`POST /skills/match-candidates`

**Request:**
```json
{
  "job_id":                "uuid",
  "member_id":             "uuid",
  "job_skills":            ["Python", "Kafka", "AWS", "Docker"],
  "resume_skills":         ["Python", "Kafka", "Kubernetes", "Go"],
  "job_location":          "San Francisco",
  "member_location":       "San Francisco, CA",
  "required_experience":   3.0,
  "member_experience":     5.0
}
```

**Response `200`:**
```json
{
  "member_id":     "uuid",
  "job_id":        "uuid",
  "match_score":   0.725,
  "skills_overlap": ["Python", "Kafka"],
  "explanation":   "Skills overlap: 2/4 (python, kafka). Location match: yes. Experience: 5.0 vs required 3.0."
}
```

`match_score` is 0.0–1.0. Computed as: skills overlap (60%) + location match (20%) + experience ratio (20%).

---

### 11.3 Start Hiring Assistant Workflow

`POST /agents/hiring-assistant/start`

Initiates an async multi-step AI workflow:  
1. Fetch job details  
2. Fetch all applications  
3. Parse each resume (Resume Parser skill)  
4. Score each candidate (Matching skill)  
5. Generate outreach drafts (LLM)  
6. Await recruiter approval (human-in-the-loop)

**Request:**
```json
{
  "job_id":       "uuid",
  "recruiter_id": "uuid",
  "top_k":        5
}
```

**Response `200`:**
```json
{
  "trace_id": "uuid",
  "status":   "running",
  "job_id":   "uuid",
  "step":     "Starting workflow",
  "shortlist": []
}
```

**Kafka:** Publishes `ai.requested` to `ai.requests`

---

### 11.4 Get Hiring Assistant Status

`POST /agents/hiring-assistant/status`

**Request:**
```json
{ "trace_id": "uuid" }
```

**Response `200`:**
```json
{
  "trace_id": "uuid",
  "status":   "awaiting_approval",
  "job_id":   "uuid",
  "step":     "Awaiting recruiter approval",
  "shortlist": [
    {
      "member_id":      "uuid",
      "match_score":    0.82,
      "skills_overlap": ["Python", "Kafka", "AWS"],
      "explanation":    "Strong skills match. 6 years experience vs required 3.",
      "outreach_draft": "Hi Jane! I came across your profile and was impressed by your distributed systems experience..."
    }
  ]
}
```

**`status` values:** `pending` | `running` | `awaiting_approval` | `approved` | `rejected` | `completed` | `failed`

---

### 11.5 Approve / Edit / Reject AI Output

`POST /agents/hiring-assistant/approve`

Human-in-the-loop checkpoint — recruiter reviews and acts on the shortlist.

**Request:**
```json
{
  "trace_id":        "uuid",
  "action":          "edit",
  "edited_outreach": "Hi Jane! We reviewed your background in distributed systems and Kafka and would love to chat about our Senior Engineer role..."
}
```

**`action` values:** `approve` | `edit` | `reject`

**Response `200`:** Updated task status object (same as 11.4)

---

### 11.6 WebSocket — Real-Time Task Progress

`WS /agents/hiring-assistant/ws/{trace_id}`

Streams task status updates to the UI as JSON frames:

```json
{ "trace_id": "uuid", "status": "running", "step": "Parsing resumes and scoring candidates", "shortlist": [] }
```

Final frame when `status` is `awaiting_approval` | `completed` | `failed`.

---

### 11.7 Career Coach

`POST /agents/career-coach`

**Request:**
```json
{
  "member_id":   "uuid",
  "job_id":      "uuid",
  "resume_text": "Optional override; fetched from profile if omitted"
}
```

**Response `200`:**
```json
{
  "headline_suggestion": "Senior Software Engineer | Distributed Systems | Kafka | Python",
  "resume_improvements": [
    "Add quantified impact metrics (e.g., reduced latency by 40%)",
    "Move skills section above work experience"
  ],
  "skills_to_add": ["Kubernetes", "Terraform"],
  "cover_letter_tips": [
    "Reference the company's known use of microservices",
    "Highlight Kafka experience specifically"
  ]
}
```

---

## 12. Kafka Topics Reference

| Topic | Partitions | Producer | Consumers | Key Payload Fields |
|-------|-----------|----------|-----------|-------------------|
| `profile.updated` | 3 | profile-service | analytics-service | `email` |
| `job.posted` | 3 | job-service | analytics-service | `title`, `company_id` |
| `job.viewed` | 3 | job-service | analytics-service | — |
| `job.saved` | 3 | job-service | analytics-service | — |
| `job.closed` | 3 | job-service | analytics-service, **application-service** | — |
| `application.submitted` | 3 | application-service | analytics-service, **ai-agent-service** | `job_id`, `member_id`, `resume_url` |
| `application.status.changed` | 3 | application-service | analytics-service | `old_status`, `new_status` |
| `message.sent` | 3 | messaging-service | analytics-service | `message_id`, `message_text` |
| `connection.requested` | 3 | connection-service | analytics-service | `receiver_id` |
| `connection.accepted` | 3 | connection-service | analytics-service, **profile-service** | `requester_id`, `receiver_id` |
| `ai.requests` | 3 | ai-agent-service | **ai-agent-service** | `job_id` |
| `ai.results` | 3 | ai-agent-service | analytics-service | `job_id`, `shortlist_count` |

**Bold** consumers perform state mutations. Others only log events.

### Async Workflow Example (End-to-End)
```
UI                     application-service          ai-agent-service
 │──POST /applications/submit──▶│                         │
 │                               │──application.submitted──▶│
 │                               │                         │ (parses resume, scores)
 │                               │                         │──ai.results──▶analytics
 │◀──WS update────────────────────────────────────────────────────────────│
```

---

## 13. Error Codes

| HTTP Code | Meaning | Example |
|-----------|---------|---------|
| `400` | Bad request — missing required field | `{ "error": "job_id required" }` |
| `401` | Unauthorized — missing token | `{ "error": "Access token required" }` |
| `403` | Forbidden — invalid token | `{ "error": "Invalid or expired token" }` |
| `404` | Not found | `{ "error": "Job not found" }` |
| `409` | Conflict — duplicate / business rule | `{ "error": "Already applied to this job" }` |
| `409` | Closed job apply | `{ "error": "Cannot apply to a closed job" }` |
| `500` | Internal server error | `{ "error": "Internal server error" }` |
| `502` | Service unavailable (gateway) | `{ "error": "Service unavailable", "service": "/api/jobs" }` |

---

## 14. Database Justification

### MySQL — Transactional Data
Used for: members, recruiters, jobs, applications, connections, skills

**Why MySQL:**
- ACID transactions needed for multi-step operations (e.g., submit application: check job status + insert + increment count atomically)
- Foreign key constraints enforce referential integrity (applications → jobs → recruiters)
- Strong query support: FULLTEXT search on job listings, JOIN queries for connections
- Schema-fixed entities with well-defined relationships

**Key indexes:**
- `members.email` — UNIQUE, fast login/duplicate check
- `jobs(status, posted_at)` — filter open jobs by recency
- `jobs FULLTEXT(title, description)` — keyword search
- `applications(job_id, member_id)` — UNIQUE, prevents duplicate applications
- `connections(member_a, member_b)` — fast neighbor lookup

### MongoDB — Unstructured / High-Volume Data
Used for: messages, event logs, AI task traces

**Why MongoDB:**
- Messages have flexible payloads; schema can evolve without migrations
- Event logs are write-heavy, append-only — MongoDB handles high ingestion well
- AI task traces contain nested, variable-length step results
- Aggregation pipeline natively supports analytics queries (funnel, geo, top-k)

**Key indexes:**
- `event_logs(event_type, timestamp)` — dashboard time-window queries
- `event_logs(idempotency_key)` — UNIQUE, prevents duplicate event writes
- `messages(thread_id, sent_at)` — paginated message history
- `ai_task_traces(trace_id)` — UNIQUE, fast trace lookup

### Redis — Cache Layer
- Caches `GET /members/:id` and `GET /jobs/:id` responses (TTL: 300s)
- Invalidated on every update/delete
- Required for performance benchmarks (Scenario B vs B+S comparison)
