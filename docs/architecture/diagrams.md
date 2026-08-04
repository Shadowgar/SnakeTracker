# Final Architecture Diagrams

## Deployment context

```mermaid
flowchart TB
    Client[Mobile or desktop PWA]
    CF[Cloudflare edge]
    Tunnel[cloudflared tunnel]
    Nginx[Nginx trusted proxy]
    Web[FastAPI web process]
    Worker[Scheduler and worker]
    DB[(SQLite on local SSD)]
    Media[(Immutable attachment versions)]
    Backup[(Encrypted off-device backup)]
    Provider[External notification provider]

    Client --> CF --> Tunnel --> Nginx --> Web
    Web --> DB
    Web --> Media
    Worker --> DB
    Worker --> Media
    Worker --> Backup
    Worker --> Provider
```

## Dependency direction

```mermaid
flowchart LR
    P[Presentation]
    A[Application]
    D[Domain]
    I[Infrastructure]
    B[Bootstrap composition root]
    P --> A --> D
    I --> A
    I --> D
    B --> P
    B --> A
    B --> I
```

## Command and multi-stream append

```mermaid
sequenceDiagram
    actor User
    participant UI as Browser
    participant Route as Route
    participant Cmd as Command handler
    participant Auth as Authorization projection
    participant Store as Event store
    participant Sync as Synchronous projections
    participant Outbox as Outbox

    User->>UI: Submit command
    UI->>Route: CSRF, idempotency key, expected versions
    Route->>Cmd: Typed command and actor context
    Cmd->>Auth: Check current capability and ownership
    Cmd->>Store: Begin atomic operation
    Store->>Store: Validate idempotency hash and every stream version
    Store->>Store: Lock/order streams deterministically
    Store->>Sync: Apply correctness projections
    Store->>Outbox: Record asynchronous work
    Store->>Store: Store versioned result and commit
    Store-->>Cmd: Events and new versions
    Cmd-->>UI: HTML fragment or API result
```

## Correction and compensation

```mermaid
flowchart LR
    Original[Original event]
    Correction[Typed correction or void event]
    Effective[Effective-state projection]
    Compensation[Cross-stream compensating event]
    Audit[Preserved historical chain]
    Original --> Audit
    Correction --> Audit
    Original --> Effective
    Correction --> Effective
    Correction -->|when required| Compensation --> Effective
```

## Projection rebuild

```mermaid
flowchart TB
    Active[Active projection generation]
    High[Capture high-water position]
    Shadow[Build shadow generation]
    Validate[Validate contracts, rows, FKs, invariants, FTS]
    Tail[Catch up tail]
    Switch[Atomic catalog activation]
    Old[Retained prior generation]
    Cleanup[Deferred cleanup]
    High --> Shadow --> Validate --> Tail --> Switch
    Active --> Old
    Switch --> Cleanup
    Validate -->|failure| Active
```

## Reminder-to-delivery pipeline

```mermaid
flowchart LR
    E[Domain events]
    F[Reminder facts]
    I[Notification intent]
    O[Transactional outbox]
    J[Durable job]
    P[Provider operation]
    A[Delivery attempt]
    E --> F --> I --> O --> J --> P
    J --> A
```

## Backup and restoration

```mermaid
sequenceDiagram
    participant Admin
    participant Worker
    participant Live as Live SQLite
    participant Copy as Completed DB copy
    participant Media as Immutable media
    participant Repo as Encrypted backup repository

    Admin->>Worker: Enqueue backup request
    Worker->>Worker: Acquire global backup lease
    Worker->>Live: SQLite online backup
    Live-->>Copy: Consistent copy
    Worker->>Copy: Read captured attachment references
    Worker->>Media: Copy referenced immutable versions
    Worker->>Repo: Store DB, media, manifest, checksums
    Worker->>Repo: Verify backup set
    Worker->>Worker: Record health and release lease
```

## Household bootstrap

```mermaid
sequenceDiagram
    participant App
    participant Store
    participant Auth as Authorization projection
    App->>Store: Begin idempotent transaction
    Store->>Store: Append household.created
    Store->>Store: Append household.owner_added
    Store->>Auth: Create active owner membership
    Store->>Store: Store command result and commit
    Auth-->>App: Current authorization available
```

## Logical entity relationships

```mermaid
erDiagram
    USERS ||--o{ SESSIONS : owns
    USERS ||--o{ MEMBERSHIP_PROJECTION : has
    HOUSEHOLDS ||--o{ MEMBERSHIP_PROJECTION : contains
    HOUSEHOLDS ||--o{ EVENT_STREAMS : scopes
    EVENT_STREAMS ||--o{ DOMAIN_EVENTS : contains
    DOMAIN_EVENTS ||--o{ EVENT_SUBJECTS : references
    DOMAIN_EVENTS ||--o{ EVENT_ATTACHMENT_REFS : references
    ATTACHMENTS ||--o{ ATTACHMENT_VERSIONS : versions
    ATTACHMENT_VERSIONS ||--o{ EVENT_ATTACHMENT_REFS : finalized_reference
    EVENT_STREAMS ||--o{ AGGREGATE_SNAPSHOTS : accelerates
    PROJECTION_DEFINITIONS ||--o{ PROJECTION_GENERATIONS : versions
    OUTBOX_ITEMS ||--o{ JOBS : hands_off
    JOBS ||--o{ DELIVERY_ATTEMPTS : attempts
    USERS ||--o{ SECURITY_AUDIT : actor
    HOUSEHOLDS ||--o{ SECURITY_AUDIT : scopes
```
