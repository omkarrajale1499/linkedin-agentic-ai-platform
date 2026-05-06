# Agent Architecture Diagram

```mermaid
flowchart TD
    R["Recruiter UI"] -->|1. Start workflow| G["API Gateway"]
    G -->|2. POST /agents/hiring-assistant/start| AI["AI Agent Service (FastAPI)"]
    AI -->|3. Publish ai.requested| K["Kafka: ai.requests"]
    K -->|4. Consume ai.requests| C["AI Kafka Consumer (ai-agent-group)"]
    C --> S["Hiring Assistant Supervisor Agent"]

    subgraph Skills["AI Skills (stateless services/modules)"]
        RP["Resume Parser Skill"]
        JM["Job-Candidate Matching Skill"]
        OD["Outreach Draft Generation"]
        CC["Career Coach Agent (optional path)"]
    end

    S --> RP
    S --> JM
    S --> OD
    S --> CC

    S --> TS["Trace Store (MongoDB ai_task_traces)"]
    S -->|5. Publish intermediate/final| KR["Kafka: ai.results"]
    KR --> AN["Analytics Service (consumer)"]

    AI -->|6. WS /agents/hiring-assistant/ws/{trace_id}| WS["WebSocket Stream"]
    WS --> R

    R -->|7. Approve/Edit/Reject| AP["POST /agents/hiring-assistant/approve"]
    AP --> AI
    AI --> TS
```

## Agent Workflow Details

Task states:

- `pending`
- `running`
- `awaiting_approval`
- `approved`
- `rejected`
- `completed`
- `failed`
- `cancelled`

Core hiring workflow:

1. Receive job + recruiter + `top_k`.
2. Fetch job details and candidate applications.
3. Parse resume text into structured fields.
4. Compute candidate match scores and explanations.
5. Build shortlist and outreach drafts.
6. Pause for human approval/edit/reject.
7. Persist final decision and publish results.

Reliability controls:

- Trace propagation via `trace_id`.
- Retry safety via idempotency keys.
- Kafka-first orchestration with inline fallback option when configured.

