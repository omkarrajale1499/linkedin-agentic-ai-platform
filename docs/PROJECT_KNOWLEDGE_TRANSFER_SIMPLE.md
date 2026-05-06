# Project Guide (Simple Version) - LinkedIn Simulation + Agentic AI

This is the easy-to-understand version for teammates. Read this first if you are new to the project.

## What this project does

We built a LinkedIn-like app where:

- Members create profiles, search jobs, apply, message, and connect.
- Recruiters post jobs, review applicants, update status, and use AI assistance.
- The backend is split into small services so it can scale and be maintained easily.

## Big picture architecture

Think of it in 3 layers:

1. **Client Layer**: React web app (what users see)
2. **Service Layer**: API Gateway + multiple backend services + Kafka
3. **Data Layer**: MySQL + MongoDB + Redis

## Main services and their jobs

- **API Gateway**: front door for all client requests.
- **Profile Service**: member/recruiter profile operations.
- **Job Service**: create/search/update/close job postings.
- **Application Service**: submit applications and track status.
- **Messaging Service**: thread and message handling.
- **Connection Service**: connection request and accept/reject.
- **Analytics Service**: stores/reads tracking events and dashboard data.
- **AI Agent Service**: runs AI workflows (shortlisting, scoring, suggestions).

## What Kafka is doing here

Kafka is our event bus.  
Services send events like:

- job posted/viewed/closed
- application submitted/status changed
- message sent
- connection requested/accepted
- AI requested/results

Why this helps:

- Services are less tightly coupled.
- Async work does not block user requests.
- Easy to add analytics and monitoring.

## Databases in simple terms

- **MySQL** = structured, transactional business data  
  (users, jobs, applications, connections)
- **MongoDB** = flexible/log-style data  
  (messages, event logs, AI traces)
- **Redis** = fast cache  
  (quick reads and reduced DB load)

## Typical user flow (simple)

### Member applies to a job

1. Member clicks Apply in UI.
2. Request goes to API Gateway -> Application Service.
3. Service writes application in MySQL.
4. Service emits Kafka event `application.submitted`.
5. Analytics/AI consumers process event.

### Recruiter uses AI assistant

1. Recruiter starts AI workflow for a job.
2. AI service publishes request to Kafka.
3. Hiring Assistant agent runs steps:
   - parse resumes
   - score candidates
   - generate outreach draft
4. Recruiter reviews output (approve/edit/reject).
5. Final status and history are saved.

## Important reliability rules

- No duplicate email accounts.
- No duplicate apply for same user and job.
- Cannot apply to closed jobs.
- Idempotency keys prevent duplicate writes during retries.
- Critical DB writes are done transactionally.

## Performance/scalability testing

We benchmarked with 100 concurrent users:

- Scenario A: job search + job detail (read-heavy)
- Scenario B: application submit (write-heavy + Kafka event)

Compared combinations:

- B (base)
- B + S (Redis caching)
- B + S + K (Kafka)
- B + S + K + extra optimizations

## Where to find detailed docs

- Full technical handover: `docs/PROJECT_KNOWLEDGE_TRANSFER_LLM.md`
- System diagram: `docs/diagrams/system-architecture.md`
- Agent diagram: `docs/diagrams/agent-architecture.md`
- Database schema: `docs/diagrams/database-schema.md`
- Full API design: `docs/api-document.md`
- Kafka topics: `docs/kafka-topics.md`

## Quick start for teammates

1. Run `docker-compose up --build`
2. Seed data using `python databases/seed.py --fast`
3. Open UI and test one member + one recruiter flow
4. Run one AI flow end-to-end
5. Read full doc when implementing or debugging

