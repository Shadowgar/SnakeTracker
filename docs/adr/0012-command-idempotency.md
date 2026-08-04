# ADR-0012: Make Command Idempotency Atomic

Status: Accepted
Acceptance date: 2026-08-04

## Context
Network retries and double taps must not create duplicate events.

## Decision
Within the command transaction, create a record unique on household, actor, operation scope, and key; bind it to a canonical command hash; store resulting events/versions, correlation, a schema-versioned sanitized result, status, and expiry. `in_progress` is never committed separately. Equivalent completed retries return the stored result; hash mismatch returns conflict. Retain completed records at least 90 days.

## Alternatives
Memory cache, event-ID-only dedupe, or separately committed ownership rows.

## Tradeoffs
Storage and canonicalization rules are required. Long-lived uniqueness uses domain identifiers rather than expiring records.

## Future impact
Stored results require compatibility/upcast policy.
