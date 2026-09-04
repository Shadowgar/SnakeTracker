# Database Schema Recommendations

This is a logical schema contract, not executable migration code. SQL names may be refined only without changing ownership, constraints, or semantics, unless an ADR is superseded.

## Authoritative event tables

### `event_streams`

- `household_id`, `stream_type`, `stream_id`
- `current_version`
- `created_at`, `updated_at`
- Unique primary key on household/type/ID
- Index on household/type and updated time

This row is the concurrency boundary and future PostgreSQL lock target.

### `domain_events`

- Integer `global_position` primary ordering key
- Unique UUID `event_id`
- Household/type/stream identity and `stream_version`
- Event contract type/version
- UTC occurred/recorded times and actor
- Correlation, causation, and originating idempotency key
- Title, description, canonical typed payload JSON, technical metadata JSON, notes
- Canonical checksum
- Unique `(household_id, stream_type, stream_id, stream_version)`
- Indexes on household/global position, stream/version, occurred time, event contract, correlation, causation, and actor/recorded time

Payloads are validated before storage. JSON expression indexes are added only for measured query needs; normal reads use projections.

### `event_subjects`, `event_tags`, `event_attachment_refs`

Normalized associations keyed by event ID. Subjects store registered type, UUID, relationship, and order. Attachment references target finalized immutable attachment-version IDs. All include household scope and uniqueness constraints preventing duplicate associations.

### `aggregate_snapshots`

Household/stream identity, stream version, snapshot schema, aggregate implementation version, boundary event, UTC creation, state blob/JSON, checksum. Unique per stream/version/schema; indexed newest-first. It is derived and safely deletable.

## Identity and authorization operations

### `users`

UUID, normalized unique email, password hash/version, account status, audit timestamps. Personal fields are minimized.

### `sessions`

UUID, user, unique token hash, created/last-seen/idle-expiry/absolute-expiry/revoked times, safe client metadata. Index token hash and expiry. Session rows are excluded or invalidated on restore.

### `password_reset_credentials`

UUID, user, unique keyed token digest, requested/expiry/consumed/invalidated times, and initiation
source (`self_service` or `operator`). The table is conventional mutable identity/security state,
not an event stream. Only one credential per user remains usable: new requests invalidate older rows,
and successful reset consumes the presented row while invalidating every other row and revoking all
user sessions in the same transaction. Raw reset tokens and URLs never enter this table. Reset rows
are removed from backup copies with sessions and other temporary credentials.

### `authorization_memberships`

Synchronous projection keyed by household/user with role, status, source stream version/global position, and updated time. Protected requests use this table and current ownership joins.

Normal self-service registration is a dedicated production application operation. It creates the
server-selected user and household identities, canonical household events, household summary, owner
membership, idempotency result, and security audit in one immediate transaction. Initial empty-install
bootstrap remains one-time, while ADR-0040 demo provisioning remains separately environment-gated.

### `security_audit`

Append-oriented integer/UUID identity, UTC time, category, outcome, actor/household/target, correlation, resolved IP, safe agent classification, and redacted details. Index time, actor, household/category, target, and correlation.

## Command and asynchronous operations

### `idempotency_operations`

Household, actor, operation scope/key, canonical command hash, status, result event/version JSON, stored response and schema version, correlation, created/completed/expiry times, safe failure classification. Unique `(household_id, actor_user_id, operation_scope, idempotency_key)`. Index expiry for bounded cleanup.

### `outbox_items`

UUID, kind, payload contract/version, logical key, correlation/causation, available time, state, creation time. Unique logical handoff key and index claim order.

### `jobs`

UUID, type, payload/version, optional household, priority, schedule, status, attempt/max attempts, lease owner/token/times, heartbeat, logical/idempotency keys, correlation/causation, timestamps, safe error, result reference. Unique job-type logical operation key; indexes for eligible claim, expired leases, and dead letters.

### `notification_intents` and `delivery_attempts`

Intent is unique by rule occurrence, recipient, and channel. Attempts are unique by job, attempt number, and lease token and store provider operation ID plus safe outcome. Provider secrets are stored separately from these records.

### `backup_operations`

Operation ID, requestor, schedule/reason, state, global lease owner/token/times, captured position, manifest/key versions, bytes/duration, verification state, safe error, and timestamps. Only one active lease is permitted.

### `inventory_balance`

Household/item identity, current name and unit, on-hand/reserved/consumed/expired quantities, reorder
threshold, active-or-archived status, source stream version/event, and updated time. This synchronous
projection is rebuildable from the immutable inventory-item stream; archive never deletes historical
consumption links or allocations.

## Attachments

### `attachments`

Logical UUID, household, status, subject ownership, created/archived audit fields.

### `attachment_versions`

Immutable UUID, attachment ID, version number, random storage key, checksum, byte size, detected media type, dimensions/page metadata, finalized time, and scan/validation outcome. Unique attachment/version and storage key. Events may reference only finalized rows, enforced by application policy and integration tests.

### `staged_uploads`

Operational, expiring staging identity with randomized path, limits, validation state, owner, and expiry. Never served directly and excluded from backups.

## Projection management

### `projection_definitions`, `projection_generations`, `projection_checkpoints`

Store stable name, schemas/handlers, consistency class, rebuild group, active generation, physical identifier selected from a registry, checkpoint, health, validation, and retention state. Catalog activation is atomic.

Physical projection tables are generation suffixed. Cross-generation foreign keys are prohibited. FTS5 has a generation-specific content table and virtual table.

## Soft deletion and audit fields

Mutable administrative resources may use `created_at`, `updated_at`, `deleted_at`, `created_by`, and `updated_by` where appropriate. Domain events are never soft deleted. Aggregate archival is a domain transition. Operational cleanup follows explicit retention policies.

## SQLite constraints

- UUIDs use one canonical representation selected in the SQLite ADR implementation appendix.
- Foreign keys are enabled and required for operational tables.
- JSON validity checks apply to JSON columns where supported.
- Bounded text and payload sizes are enforced at application and database levels where practical.
- Partial indexes support active sessions, eligible jobs, expiring idempotency records, and finalized attachments.
- Write transactions remain short; analytical queries use projections rather than event JSON scans.
