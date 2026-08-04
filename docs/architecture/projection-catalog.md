# Projection Catalog and Recovery Model

## Consistency classes

| Projection/group | Purpose | Consistency |
|---|---|---|
| `authorization_memberships` | Current membership, roles, account/household access | Synchronous |
| `animal_current` | Profile, lifecycle, enclosure, latest measurements | Synchronous |
| `animal_effective_timeline` | Effective history and correction chain | Synchronous initially |
| `health_current` | Active medication and material health state | Synchronous |
| `enclosure_current` | Enclosure state and maintenance due facts | Synchronous |
| `enclosure_occupancy` | Current projected occupancy from animal streams | Synchronous |
| `inventory_balance` | Available, reserved, consumed, expired quantities | Synchronous |
| `reminder_rule_current` | Effective reminder-rule state | Synchronous |
| `reminder_facts` | Due/overdue factual inputs | Synchronous where command correctness depends on them; otherwise asynchronous |
| `document_catalog` | Finalized version and subject ownership | Synchronous |
| `tag_index` | Effective normalized tag associations | Synchronous initially |
| `global_search_fts` | Authorized FTS5 search | Asynchronous |
| `measurement_analytics` | Growth and measurement statistics | Asynchronous |
| `feeding_analytics` | Intervals, refusals, and consumption statistics | Asynchronous |
| `report_facts` | Normalized report facts | Asynchronous |
| `dashboard_statistics` | Expensive counts and trends | Asynchronous |
| `notification_candidates` | Inputs for intent generation | Asynchronous |
| `aggregate_snapshots` | Command replay acceleration | Asynchronous |

Moving a projection into the synchronous command transaction requires a measured correctness or user-experience need and an ADR impact review.

## Projection definition

Each projection declares a stable name, schema version, handler version, supported event contracts, consistency class, rebuild group, correction/reversal behavior, last processed global position, health, last error, and active generation.

Asynchronous projections consume transactional outbox work in global-position order and expose freshness. A lagging or unavailable analytical projection cannot corrupt authoritative state.

## Rebuild and activation

1. Capture an event-store high-water global position.
2. Create generation-specific shadow storage.
3. Replay registered contracts in global order.
4. Validate handler coverage, row counts, invariants, checksums where defined, and checkpoint.
5. Process events after the captured high-water position.
6. Acquire the projection-group activation lock.
7. Apply the final tail and atomically publish the generation in the projection catalog.
8. Retain the previous generation through health verification.
9. Clean it later using a resumable job.

Ordinary tables use generation suffixes. Projection-internal foreign keys reference only the same generation, and interdependent tables swap as one group after `foreign_key_check`. Views are versioned within the group. FTS5 builds a generation-specific content and virtual table, runs integrity and optimization checks, then switches the catalog pointer. Query repositories accept only registry-generated physical identifiers.

Failure or interruption before activation preserves the current generation. Failure after activation can atomically restore the previous catalog pointer while it remains retained. Authorization fails closed if no trusted active authorization generation exists.

## Required evidence

Integration evidence must demonstrate successful swap, pre-activation validation failure, replay interruption, interruption around activation, tail catch-up under writes, rollback, foreign-key/interdependent consistency, FTS activation, and resumable cleanup.
