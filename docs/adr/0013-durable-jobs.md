# ADR-0013: Use Leased Durable Jobs and At-Least-Once Effects

Status: Accepted
Acceptance date: 2026-08-04

## Context
Workers crash and external systems can accept work before local completion is recorded.

## Decision
Persist versioned jobs with schedule, priority, attempts, maximum attempts, lease owner/token/times, heartbeat, logical key, correlation, result, and dead-letter state. Expired leases are reclaimable. External execution is at least once; every handler declares provider idempotency, durable external-ID reconciliation, read-before-write reconciliation, or bounded duplicate tolerance.

## Alternatives
In-memory scheduling, exactly-once claims, or synchronous provider calls.

## Tradeoffs
Reconciliation and visible uncertain states are required.

## Future impact
Distributed workers can reuse the lease contract after PostgreSQL migration.
