# ADR-0038: Separate Effective-History Scheduling from Husbandry Suggestions

Status: Accepted
Acceptance date: 2026-08-10

## Context

Fixed dates cannot express keeper-configured schedules relative to effective husbandry history.
Later analytics and curated species guidance must not overwrite owner schedules, invent veterinary
advice, or become new business aggregates.

## Decision

M5 Reminder Rule streams own fixed-interval and event-relative schedule policy, per-animal owner
configuration, enablement, and explicit overrides. Rebuildable reminder facts consume the latest
effective qualifying Animal or Enclosure history, retain calculation provenance, and recalculate
after correction, void, reinstatement, replay, or rebuild. Owner configuration is authoritative;
M5 contains no species recommendations.

M6 may add read-side trends, interval statistics, and explainable estimated feeding or shed windows.
Optional species/life-stage husbandry reference profiles are versioned curated reference data with
source provenance. They prefer ranges, never fabricate missing guidance, and cannot silently replace
owner schedules. Analytics, profiles, and recommendations own no write aggregate and do not alter
Animal, Enclosure, or Reminder Rule streams. Deterministic rules/statistics are distinct from the
deferred AI assistant.

## Effective-history policy

Feeding schedules use the latest effective accepted feeding. Refused attempts do not reset the
schedule. Regurgitated is not treated as accepted; changing that interpretation requires an explicit
contract/policy amendment rather than inference. Weight, length, bath/soak, enclosure cleaning, and
water-change schedules use the latest effective event of their corresponding qualifying type.

Facts retain the governing rule/version, schedule kind, configured interval or due-date override,
source kind and effective occurred time, calculated due time, and a technical source reference.
Keeper views explain the calculation without exposing raw identifiers by default.

## Alternatives

Fixed calendar dates only; species defaults embedded in commands; predictions as write aggregates;
or raw-event-chronology scheduling were rejected because they are not keeper-configurable,
correction-safe, or compatible with the established event/projection boundary.

## Compatibility, testing, and migration impact

No M3 or M4 event is rewritten. Reminder contracts begin as new M5 contracts, and reminder facts
are rebuildable relational/read-side state. M5 tests cover fixed/event-relative rules, effective
fallback, correction/void/reinstatement, timezone/DST, replay/rebuild, repeat scans, restart, and
deduplication. M6 reference-profile schemas require explicit data/profile versions and provenance;
unknown newer versions fail safely under the release compatibility policy.

## Roadmap impact

M5 gains effective-history scheduling and explainable reminder-fact qualification. M6 explicitly
retains analytics, estimated windows, due/overdue presentation, and optional curated reference
profiles. No Phase 6 implementation is pulled into M5.
