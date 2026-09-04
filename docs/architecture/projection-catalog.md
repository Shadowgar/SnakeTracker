# Projection Catalog and Recovery Model

## Consistency classes

| Projection/group | Purpose | Consistency |
|---|---|---|
| `authorization_memberships` | Current membership, roles, account/household access | Synchronous |
| `animal_current` | Profile, registered capability profile, lifecycle, enclosure, latest applicable measurements | Synchronous |
| `animal_effective_timeline` | Effective history and correction chain | Synchronous initially |
| `molt_history` | Effective Spider/Scorpion molt and premolt history across schema v1/v2 | Synchronous initially |
| `health_current` | Active medication and material health state | Synchronous |
| `enclosure_current` | Enclosure state and maintenance due facts | Synchronous |
| `enclosure_occupancy` | Current projected occupancy from animal streams | Synchronous |
| `inventory_balance` | Available, reserved, consumed, expired quantities | Synchronous |
| `reminder_rule_current` | Effective reminder-rule state | Synchronous |
| `reminder_facts` | Explainable due/overdue facts from owner rules and effective care history | Synchronous where command correctness depends on them; otherwise asynchronous |
| `document_catalog` | Finalized version and subject ownership | Synchronous |
| `tag_index` | Effective normalized tag associations | Synchronous initially |
| `global_search_fts` | Authorized FTS5 search | Asynchronous |
| `measurement_analytics` | Growth and measurement statistics | Asynchronous |
| `feeding_analytics` | Intervals, refusals, and consumption statistics | Asynchronous |
| `report_facts` | Normalized report facts | Asynchronous |
| `dashboard_statistics` | Expensive counts and trends | Asynchronous |
| `notification_candidates` | Inputs for intent generation | Asynchronous |
| `husbandry_reference_profiles` | Optional versioned curated species/life-stage ranges with source provenance | Read-only reference data introduced in M6 |
| `husbandry_recommendations` | Explainable estimated windows from owner rules, effective history, and optional references | Asynchronous in M6 |
| `aggregate_snapshots` | Command replay acceleration | Asynchronous |

Moving a projection into the synchronous command transaction requires a measured correctness or user-experience need and an ADR impact review.

## Projection definition

Each projection declares a stable name, schema version, handler version, supported event contracts, consistency class, rebuild group, correction/reversal behavior, last processed global position, health, last error, and active generation.

Asynchronous projections consume transactional outbox work in global-position order and expose freshness. A lagging or unavailable analytical projection cannot corrupt authoritative state.

Reminder facts consume only care kinds registered for the subject's capability profile. Shared
sources include effective feeding and applicable measurements; profile-scoped sources include
snake shed/bath and v1/v2 molt/premolt. Enclosure-owned cleaning and water-change sources require no
Animal capability profile. Configured misting requires a currently assigned capable occupant and
the event's related Animal subject.
Corrections, voids, and reinstatements therefore change their factual source and trigger deterministic
recalculation. Each fact retains rule version, schedule kind, interval/override, source type and
effective occurrence time, calculation time, and a technical source reference so the keeper view can
explain the result without exposing event UUIDs.

M6 analytics and recommendations remain read-side consumers; they do not own write aggregates.
Their stable M5.5 inputs are animal type/capability identity, effective feeding history, applicable
measurements, snake shed history, Spider/Scorpion molt history, reminder facts, and neutral enclosure-care
facts. Search and reports index a common animal document plus allow-listed capability-specific
fields. Missing or inapplicable facts are not interpreted as zero, overdue, or negative evidence.
Versioned husbandry reference profiles are curated reference data with explicit sources and profile
versions. Missing guidance remains missing, ranges are preferred over false precision, and owner
schedules remain authoritative. Deterministic suggestions are not the deferred AI-assistant feature.

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
