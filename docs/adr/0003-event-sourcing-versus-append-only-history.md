# ADR-0003: Prefer Event Sourcing to an Append-Only Audit History

Status: Accepted
Acceptance date: 2026-08-04

## Context
An append-only audit table beside mutable current-state rows would be simpler but could disagree with state and could not reliably rebuild it.

## Decision
The domain event store is authoritative and projections are derived. This is justified because animal care is longitudinal, corrections must remain visible, most requested reports are temporal, event volume is moderate, and future rules/AI can re-derive facts.

## Alternatives
A CRUD model with audit rows; full event sourcing of operational state.

## Tradeoffs
The project accepts contract versioning, deterministic replay, projection recovery, and stricter testing. It avoids applying event sourcing where history is not useful.

## Future impact
If event-platform cost exceeds demonstrated product value, changing authority requires a migration ADR and integrity proof.
