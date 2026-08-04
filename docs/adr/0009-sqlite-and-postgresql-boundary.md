# ADR-0009: Use SQLite for V1 with a PostgreSQL Boundary

Status: Accepted
Acceptance date: 2026-08-04

## Context
The target is one Pi and one household, while future SaaS may require concurrent distributed writes.

## Decision
Use SQLite on local SSD for v1. Isolate storage through application-owned ports, deterministic stream locking order, portable SQL where practical, and UUID identities. Require PostgreSQL review before organizations, horizontal scaling, or sustained write contention beyond budgets.

## Alternatives
PostgreSQL from day one or a database embedded without abstraction.

## Tradeoffs
SQLite minimizes operations but serializes writes and makes some swap/locking techniques implementation-specific.

## Future impact
Migration must preserve global/event ordering semantics, expected versions, idempotency, and projection checkpoints.
