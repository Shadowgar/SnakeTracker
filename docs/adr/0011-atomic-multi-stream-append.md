# ADR-0011: Atomically Append Across Streams

Status: Accepted
Acceptance date: 2026-08-04

## Context
Feeding plus inventory consumption and similar workflows affect multiple aggregates.

## Decision
A multi-stream append supplies expected versions for every stream, validates all before insert, orders streams lexically by household/type/UUID, and commits events, synchronous projections, outbox, and idempotency result in one transaction.

## Alternatives
Eventual process-manager compensation for every workflow or uncoordinated sequential writes.

## Tradeoffs
Transactions must remain short and should touch few streams. Genuine concurrent conflicts require retry/user resolution.

## Future impact
PostgreSQL implementations acquire locks in the same deterministic order.
