# Database Schema (MySQL + MongoDB + Redis)

## MySQL ER Diagram

```mermaid
erDiagram
    MEMBERS {
        varchar member_id PK
        varchar first_name
        varchar last_name
        varchar email UK
        varchar password_hash
        varchar phone
        varchar city
        varchar state
        varchar country
        varchar headline
        text about
        varchar profile_photo_url
        varchar resume_url
        longtext resume_text
        int connections_count
        tinyint is_deleted
        datetime created_at
        datetime updated_at
    }

    MEMBER_SKILLS {
        int id PK
        varchar member_id FK
        varchar skill
    }

    MEMBER_EXPERIENCE {
        int id PK
        varchar member_id FK
        varchar title
        varchar company
        varchar location
        date start_date
        date end_date
        boolean is_current
        text description
    }

    MEMBER_EDUCATION {
        int id PK
        varchar member_id FK
        varchar school
        varchar degree
        varchar field_of_study
        year start_year
        year end_year
    }

    RECRUITERS {
        varchar recruiter_id PK
        varchar company_id
        varchar first_name
        varchar last_name
        varchar email UK
        varchar password_hash
        varchar phone
        varchar company_name
        varchar company_industry
        varchar company_size
        varchar role
        tinyint is_deleted
        datetime created_at
        datetime updated_at
    }

    PROFILE_VIEWS {
        int id PK
        varchar member_id FK
        varchar viewer_id
        datetime viewed_at
    }

    JOBS {
        varchar job_id PK
        varchar company_id
        varchar recruiter_id FK
        varchar title
        longtext description
        varchar seniority_level
        varchar employment_type
        varchar city
        varchar state
        varchar country
        varchar work_mode
        decimal salary_min
        decimal salary_max
        varchar industry
        varchar status
        int views_count
        int applicants_count
        int saves_count
        datetime posted_at
        datetime closed_at
        datetime updated_at
    }

    JOB_SKILLS {
        int id PK
        varchar job_id FK
        varchar skill
    }

    SAVED_JOBS {
        int id PK
        varchar member_id FK
        varchar job_id FK
        datetime saved_at
    }

    APPLICATIONS {
        varchar application_id PK
        varchar job_id FK
        varchar member_id FK
        varchar resume_url
        longtext resume_text
        text cover_letter
        varchar status
        varchar idempotency_key UK
        datetime applied_at
        datetime updated_at
    }

    APPLICATION_NOTES {
        int id PK
        varchar application_id FK
        varchar recruiter_id
        text note
        datetime created_at
    }

    APPLICATION_STATUS_HISTORY {
        int id PK
        varchar application_id FK
        varchar old_status
        varchar new_status
        varchar changed_by
        datetime changed_at
    }

    CONNECTION_REQUESTS {
        varchar request_id PK
        varchar requester_id FK
        varchar receiver_id FK
        varchar status
        varchar message
        varchar idempotency_key UK
        datetime created_at
        datetime updated_at
    }

    CONNECTIONS {
        int id PK
        varchar member_a FK
        varchar member_b FK
        datetime connected_at
    }

    POSTS {
        varchar post_id PK
        varchar author_id FK
        text content
        varchar post_type
        int likes_count
        int comments_count
        datetime created_at
        datetime updated_at
    }

    POST_LIKES {
        varchar like_id PK
        varchar post_id FK
        varchar member_id FK
        datetime created_at
    }

    POST_COMMENTS {
        varchar comment_id PK
        varchar post_id FK
        varchar author_id FK
        text content
        datetime created_at
        datetime updated_at
    }

    SAVED_POSTS {
        varchar save_id PK
        varchar post_id FK
        varchar member_id FK
        datetime created_at
    }

    MEMBERS ||--o{ MEMBER_SKILLS : has
    MEMBERS ||--o{ MEMBER_EXPERIENCE : has
    MEMBERS ||--o{ MEMBER_EDUCATION : has
    MEMBERS ||--o{ PROFILE_VIEWS : receives

    RECRUITERS ||--o{ JOBS : posts
    JOBS ||--o{ JOB_SKILLS : requires
    MEMBERS ||--o{ SAVED_JOBS : saves
    JOBS ||--o{ SAVED_JOBS : saved_by

    MEMBERS ||--o{ APPLICATIONS : submits
    JOBS ||--o{ APPLICATIONS : receives
    APPLICATIONS ||--o{ APPLICATION_NOTES : annotated_by_recruiter
    APPLICATIONS ||--o{ APPLICATION_STATUS_HISTORY : changes

    MEMBERS ||--o{ CONNECTION_REQUESTS : sends
    MEMBERS ||--o{ CONNECTION_REQUESTS : receives
    MEMBERS ||--o{ CONNECTIONS : member_a
    MEMBERS ||--o{ CONNECTIONS : member_b

    MEMBERS ||--o{ POSTS : writes
    POSTS ||--o{ POST_LIKES : has
    POSTS ||--o{ POST_COMMENTS : has
    MEMBERS ||--o{ POST_LIKES : likes
    MEMBERS ||--o{ POST_COMMENTS : comments
    POSTS ||--o{ SAVED_POSTS : saved
    MEMBERS ||--o{ SAVED_POSTS : saves
```

## MongoDB Schema Map

```mermaid
flowchart LR
    subgraph MDB["MongoDB: linkedin_ds_logs"]
        T["threads\n- participant_ids[]\n- updated_at\nIndexes: participant_ids, updated_at"]
        M["messages\n- thread_id\n- sender_id\n- message_text\n- sent_at\n- idempotency_key\nIndexes: (thread_id,sent_at), sender_id, unique sparse idempotency_key"]
        E["event_logs\n- event_type\n- trace_id\n- actor_id\n- entity\n- payload\n- timestamp\n- idempotency_key\nIndexes: event_type+timestamp, actor_id, entity.entity_id, trace_id, unique sparse idempotency_key"]
        A["ai_task_traces\n- trace_id\n- status\n- history[]\n- shortlist[]\n- created_at\nIndexes: unique trace_id, status, created_at, history.timestamp"]
    end
```

## Redis Usage

Redis is used as a cache layer for high-read and gateway-adjacent workloads.

Typical patterns:

- Cache hot member/job lookups.
- Invalidate cache on update/delete.
- Reduce repeated database hits under concurrency.

