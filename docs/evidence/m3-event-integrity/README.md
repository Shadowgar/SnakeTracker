# M3 Event Integrity Evidence

Status: M3 implementation-qualified; owner acceptance pending

This evidence proves the Phase 3 general event platform on the approved laptop/Docker development
environment. It does not grant Raspberry Pi deployment qualification and does not authorize Phase
4 functionality.

## Result

All applicable M3 release blockers and the development qualification target pass. The controlling
[milestone checklist](../../roadmap/milestones.md#phase-3--m3--event-integrity-proven) remains
pending owner acceptance even though its evidence-backed technical criteria are checked.

- [Tests and requirement mapping](tests/README.md)
- [Migration lifecycle](operations/migration.md)
- [Container and ARM64 compatibility](containers/README.md)
- [One-million-event performance and growth qualification](performance/laptop-container/summary.md)
- `evidence-manifest.json` records provenance and classification.
- `checksums.sha256` covers the retained M3 evidence set.

## Scope controls

Synthetic contracts and projections use the reserved test namespace, live only under `tests/`,
and were injected only into test-created registries and the isolated qualification container. The
production registry contains household and generic historical-control contracts only. No generic
public event API, animal contract, Phase 4 table, outbox worker, durable job, notification, or
external side effect was introduced.

The benchmark uses the one-million-event count and category percentages from
`snaketracker-reference-v1` as a Phase 3 event-platform slice. It intentionally substitutes
reserved synthetic payloads because Phase 4 product contracts do not yet exist; this is stated in
the machine-readable result and does not load those contracts into production.

Native Raspberry Pi execution, SSD/ext4 placement, thermal behavior, and deployment performance
remain deferred to Phase 7/pre-deployment under ADR-0036.
