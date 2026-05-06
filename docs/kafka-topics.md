# Kafka Topics

All messages use the standard JSON envelope:
```json
{
  "event_type": "...",
  "trace_id": "uuid",
  "timestamp": "ISO-8601",
  "actor_id": "member_id or recruiter_id",
  "entity": { "entity_type": "job|application|thread|connection|ai_task", "entity_id": "..." },
  "payload": { ... },
  "idempotency_key": "uuid"
}
```

| Topic | Producer | Consumers | Description |
|-------|----------|-----------|-------------|
| `profile.updated` | profile-service | analytics-service | Member profile created/updated |
| `profile.viewed` | profile-service | analytics-service | Member profile viewed |
| `job.posted` | job-service | analytics-service | New job created |
| `job.viewed` | job-service | analytics-service | Job detail viewed |
| `job.saved` | job-service | analytics-service | Job saved by member |
| `job.closed` | job-service | analytics-service, application-service | Job closed by recruiter |
| `application.submitted` | application-service | analytics-service, ai-agent-service | Application submitted |
| `application.status.changed` | application-service | analytics-service | Status updated by recruiter |
| `message.sent` | messaging-service | analytics-service | Message sent in thread |
| `connection.requested` | connection-service | analytics-service | Connection request sent |
| `connection.accepted` | connection-service | analytics-service, profile-service | Connection accepted |
| `connection.rejected` | connection-service | analytics-service | Connection request rejected |
| `ai.requests` | ai-agent-service | ai-agent-service | AI task dispatch |
| `ai.results` | ai-agent-service | analytics-service | AI task completion |
