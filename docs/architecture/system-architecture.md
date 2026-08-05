# SnakeTracker System Architecture

Status: Approved
Acceptance date: 2026-08-04
Target: Raspberry Pi 5, 8 GB RAM, local SSD, Docker Compose

Primary development through Phase 6 uses Docker on the development laptop. amd64 execution,
automated tests, Compose validation, and linux/arm64 image builds qualify the development
foundation. Native Raspberry Pi execution and target storage/performance qualification occur in
Phase 7 or immediately before Pi deployment and remain mandatory for that deployment. See
ADR-0036.

## Purpose and scope

SnakeTracker is a self-hosted, mobile-first progressive web application for reptile keepers. Version 1 supports multiple users in one household and is tenant-ready without implementing full organizations. It uses a modular monolith, an event-sourced business core, synchronous correctness projections, asynchronous analytical projections, and conventional operational records.

The first production deployment uses Python 3.13+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, SQLite with FTS5, Jinja2, Bootstrap 5, HTMX, Alpine CSP build, Chart.js, Nginx, Docker Compose, and Cloudflare Tunnel. It does not require Node.js at runtime.

## Architectural principles

1. Business-state transitions are immutable domain events. Sessions, leases, caches, projections, delivery attempts, and similar operational state are relational records, not event streams.
2. One deployable modular monolith is divided by bounded context. Dependencies point inward; the FastAPI startup package is the sole composition root.
3. Domain and application layers own interfaces. Infrastructure provides implementations.
4. Every household-owned operation is authorized against the current authorization projection.
5. A command either commits its events, correctness projections, outbox entries, and idempotency result together or commits nothing.
6. External side effects occur outside the command transaction and execute at least once.
7. Read models are disposable and rebuildable; the event store is authoritative.
8. Mobile accessibility, strict CSP, recoverability, and measurable Pi performance are release criteria.
9. Plugins are trusted, startup-loaded Python packages, not sandboxed extensions.
10. Architecture changes after approval require a new or superseding ADR.

## System context

The supported request path is client to Cloudflare to cloudflared to Nginx to FastAPI. Direct public access to Nginx or FastAPI is prohibited. The deployment contains an Nginx service, one web process initially, one scheduler/worker process, and an optional backup agent controlled only by the worker. SQLite and immutable attachment storage reside on a local SSD.

See [diagrams](diagrams.md) for context, component, command, correction, rebuild, notification, and restoration flows.

## Layering and composition

- **Domain:** aggregates, value objects, policies, typed event contracts, correction capabilities, and ports that express domain needs. It imports no framework or infrastructure code.
- **Application:** command/query handlers, authorization orchestration, units of work, process managers, and ports for persistence and external capabilities.
- **Presentation:** HTML routes, API v1 routes, forms, view models, templates, and stable error representations.
- **Infrastructure:** SQLAlchemy, SQLite, event store, projection storage, filesystem/object storage, notification providers, scheduler, and security adapters.
- **Bootstrap:** validates compatibility, builds the event/plugin registry, constructs infrastructure implementations, injects handlers, and mounts routes. It is the only composition root.

The intended source tree is documented in the [folder-structure contract](folder-structure.md), [ADR-0001](../adr/0001-modular-monolith.md), and [ADR-0004](../adr/0004-aggregate-and-stream-boundaries.md). Husbandry and health are feature slices within the Animals bounded context because they write the animal stream. They do not import one another.

## Event store

Each aggregate instance owns one stream. Stored events have a unique `event_id`; `event_type + schema_version` identifies the event contract. The envelope also includes household, stream identity and version, global position, UTC `occurred_at` and `recorded_at`, actor, correlation, causation, idempotency key, typed subject references, title, description, typed payload, technical metadata, notes, tags, finalized immutable attachment-version references, and an ordinary corruption checksum.

Expected versions are supplied for every stream affected by a command. Multi-stream operations order streams lexically by `(household_id, stream_type, stream_id)` and commit atomically. Corrections, voids, reinstatements, and compensations append new events. Stored historical events are not edited in normal operation.

Snapshots are rebuildable command-side replay accelerators. They include snapshot schema, aggregate implementation, stream version, boundary event, UTC creation time, state, and checksum. Invalid or incompatible snapshots are ignored. Initial policy evaluates after append, creates a snapshot after 100 new events or replay p95 above 50 ms, avoids streams below 50 events, and retains the newest two valid snapshots.

See the [event catalog](event-catalog.md) and ADRs 0002–0006, 0011, and 0012.

## Projection model

Authorization, command-invariant, current-state, and inventory projections update synchronously. FTS5 search, report facts, expensive dashboard statistics, snapshots, and other noncritical analytics update asynchronously from transactional outbox work.

Projection definitions declare schema and handler versions, supported event contracts, consistency class, correction behavior, checkpoint, health, rebuild group, and activation strategy. Rebuilds use generation-specific shadow storage, replay to a captured high-water position, validate, catch up the tail, and atomically activate a generation. Failed or interrupted rebuilds leave the prior generation active. See the [projection catalog](projection-catalog.md) and ADRs 0007–0008.

## Operational processing

The worker owns scheduling and backup initiation. Durable jobs use leases, heartbeats, expiry, bounded retries, dead-letter state, and stable logical-operation keys. External effects are at least once, so every adapter declares provider idempotency, durable external-operation reconciliation, read-before-write reconciliation, or documented bounded duplicate tolerance.

Reminder facts, notification intent, outbox handoff, durable delivery job, delivery attempt, and provider operation are separate records with separate deduplication keys. See ADRs 0013–0014.

## Data and storage

SQLite is the v1 event store and operational database. It must use a local SSD filesystem with reliable locking. WAL, full durability, busy timeout, checkpoints, integrity checks, incremental vacuum, statistics, and FTS maintenance are governed by ADR-0010. PostgreSQL replacement is isolated behind application-owned ports and becomes mandatory before horizontal SaaS scaling.

Logical tables, constraints, and indexes are defined in the [database schema recommendations](database-schema.md).

Attachments are staged, inspected, finalized into immutable versions, and referenced only after finalization. Active content is rejected by default. Authorized delivery uses a controlled media endpoint or isolated origin with safe headers. See ADR-0017.

All persisted instants are timezone-aware UTC with microsecond precision. Household display and calendar reporting use the configured IANA timezone. Ordering uses stream versions and global position, not timestamps.

## Security and privacy

Authentication uses Argon2id password hashes and opaque server-side sessions with hashed tokens. Browser writes require CSRF protection. Capability-based household authorization is checked for every protected request against the current projection. Strict CSP, safe proxy handling, upload isolation, rate limiting, secure headers, redacted logs, dependency pinning, and append-oriented security auditing are mandatory before remote deployment.

See the [threat model](../security/threat-model.md), [security architecture](../security/security-architecture.md), and ADRs 0015–0017, 0023, and 0029–0033.

## PWA and UX

The interface is server-rendered and progressively enhanced. The initial service worker caches versioned public shell assets and a safe offline page only. Authenticated HTML and API data are not generally cached, and writes require connectivity. Draft persistence is denied by default and limited to reviewed low-sensitivity allow-listed forms with expiry and clearing rules.

The accessibility target is WCAG 2.2 AA. Core interactions require semantic structure, keyboard access, visible focus, accessible error summaries, live-region behavior for HTMX updates, reduced motion, adequate contrast, and non-chart alternatives. See the [UX information architecture](../ux/information-architecture.md) and ADRs 0020–0021.

## API and concurrency

Browser routes return pages or HTMX fragments; `/api/v1` returns stable JSON resources and command results. Aggregate resources expose strong version ETags. A stale `If-Match` produces 412; missing required preconditions may produce 428. Explicit command expected-version conflicts, business conflicts, and mismatched idempotency reuse produce typed 409 responses. Multi-stream commands carry all expected versions.

## Backup and recovery

The worker is the sole backup initiator and holds a durable global lease. A consistent SQLite backup is completed first; finalized attachment references and the attachment manifest are then read from that copy. Backup sets preserve password hashes, invalidate or omit sessions and temporary credentials, exclude plaintext secrets and decryption keys, and use independently managed encryption keys.

Restoration occurs in explicit maintenance mode into a new location, followed by integrity, compatibility, attachment, authorization, projection, and smoke-test checks before atomic activation. See the [runbook](../operations/backup-and-restoration.md) and ADR-0018.

## Performance and capacity

Qualification uses the pinned environment and versioned representative dataset: 10 users, 500 animals, 1,000 enclosures, 1,000,000 events, 100,000 attachment records, a 20 GiB attachment corpus, and 10 concurrent interactive users. Targets include steady application memory at or below 512 MiB, command p95 at or below 400 ms, HTML/HTMX p95 at or below 300 ms, FTS p95 at or below 500 ms, post-snapshot replay p95 at or below 50 ms, and a one-million-event projection rebuild within 30 minutes.

All resource ratios and sizes are qualification targets for that exact dataset and environment, not universal guarantees. See [representative dataset](../quality/representative-dataset.md) and ADR-0024.

## Release boundaries

After Phase 4, SnakeTracker must produce an **internal minimum usable baseline** containing secure household access, animal profiles, feedings, measurements, sheds, enclosures, cleaning, timeline, and basic backup capability. This release is for controlled internal operation only. It is not approved for remote/public deployment or the final production launch.

Remote deployment additionally requires all RD-class security, proxy, recovery, monitoring, and operational controls. The final production launch occurs only at M8. See [milestones](../roadmap/milestones.md).

## Architecture governance

This package became the approved architecture baseline on 2026-08-04, and the decision freeze is active. Later architectural changes must add or supersede an ADR and document migration, compatibility, testing, schedule, evidence, and milestone consequences. Silent architectural drift is a release blocker.
