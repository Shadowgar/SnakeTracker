# ADR-0021: Make V1 Offline Read-Only

Status: Accepted
Acceptance date: 2026-08-04

## Context
Offline writes require client queues, conflict resolution, local protection, and distributed synchronization.

## Decision
Cache only versioned public shell assets and a safe offline page. Do not generally cache authenticated HTML/API data. Require connectivity for mutations. Deny draft persistence by default; permit only individually reviewed low-sensitivity forms with expiry and explicit/automatic clearing.

## Alternatives
Offline event creation or full offline editing.

## Tradeoffs
Users cannot record while disconnected, but v1 avoids unsafe local data and synchronization ambiguity.

## Future impact
Offline writes require a dedicated threat model, conflict model, and ADR.
