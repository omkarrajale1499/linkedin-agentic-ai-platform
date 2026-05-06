# System Architecture Diagram

```mermaid
flowchart LR
    %% =========================
    %% Tier 1 - Client
    %% =========================
    subgraph T1["Tier 1 - Client"]
        UI["React Web Client<br/>Member + Recruiter Modules"]
    end

    %% =========================
    %% Tier 2 - Services
    %% =========================
    subgraph T2["Tier 2 - API Gateway + Microservices"]
        GW["API Gateway :3000<br/>Auth + Routing"]
        PS["Profile Service :3001"]
        JS["Job Service :3002"]
        APS["Application Service :3003"]
        MS["Messaging Service :3004"]
        CS["Connection Service :3005"]
        ANS["Analytics Service :3006"]
        AIS["AI Agent Service :8000 (FastAPI)"]
    end

    %% =========================
    %% Messaging backbone
    %% =========================
    subgraph KB["Kafka Backbone"]
        K["Kafka Broker"]
        KT["Topics<br/>profile.updated<br/>job.posted|viewed|saved|closed<br/>application.submitted|status.changed<br/>message.sent<br/>connection.requested|accepted|rejected<br/>ai.requests|ai.results"]
        K --> KT
    end

    %% =========================
    %% Tier 3 - Data
    %% =========================
    subgraph T3["Tier 3 - Datastores"]
        MYSQL["MySQL<br/>Transactional entities"]
        MONGO["MongoDB<br/>Messages, logs, AI traces"]
        REDIS["Redis<br/>Cache layer"]
    end

    %% Client to gateway
    UI -->|REST| GW

    %% Gateway to services
    GW --> PS
    GW --> JS
    GW --> APS
    GW --> MS
    GW --> CS
    GW --> ANS
    GW --> AIS

    %% Services to data
    PS --> MYSQL
    JS --> MYSQL
    APS --> MYSQL
    CS --> MYSQL

    MS --> MONGO
    ANS --> MONGO
    AIS --> MONGO

    GW <--> REDIS
    PS <--> REDIS
    JS <--> REDIS
    AIS <--> REDIS

    %% Kafka producers
    PS -->|produce events| K
    JS -->|produce events| K
    APS -->|produce events| K
    MS -->|produce events| K
    CS -->|produce events| K
    AIS -->|produce ai.results| K

    %% Kafka consumers
    K -->|consume| ANS
    K -->|consume job.closed| APS
    K -->|consume ai.requests| AIS
    K -->|consume connection.accepted| PS
```

## Notes

- All client traffic enters through API Gateway.
- Kafka decouples producers and consumers for async workflows.
- MySQL handles relational transactional data; MongoDB handles logs/traces/messages; Redis accelerates hot reads.

