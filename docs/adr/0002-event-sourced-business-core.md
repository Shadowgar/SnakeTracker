# ADR-0002: Event-Source the Business Core Only

Status: Accepted
Acceptance date: 2026-08-04

## Context
Husbandry history, corrections, trends, reports, and future derived insights require durable temporal facts.

## Decision
Meaningful business transitions are immutable domain events. Credentials, sessions, job leases, caches, projections, outbox delivery attempts, and other operational records use conventional relational state.

## Alternatives
Event-source everything, or use only current relational state.

## Tradeoffs
Replay and schema-evolution complexity is accepted where history provides product value, while operational complexity remains bounded.

## Future impact
New records must be classified explicitly as business history or operational state.
