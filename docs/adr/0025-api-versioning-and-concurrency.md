# ADR-0025: Version APIs and Make Concurrency Explicit

Status: Accepted
Acceptance date: 2026-08-04

## Context
Browser and machine clients need stable contracts and protection from lost updates.

## Decision
Expose `/api/v1`, stable problem details, cursor pagination, allow-listed filtering, and public representations independent of projection tables. Use strong version ETags and `If-Match` for resource mutations: stale produces 412 and missing required precondition may produce 428. Commands carry explicit expected stream versions; concurrency, business conflicts, and idempotency-hash mismatch produce typed 409 responses.

## Alternatives
Last-write-wins, URL-unversioned APIs, or raw database models.

## Tradeoffs
Clients must retain versions and handle conflicts accessibly.

## Future impact
Breaking public changes require a new API version and compatibility window.
