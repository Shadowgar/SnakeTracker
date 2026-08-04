# ADR-0026: Separate Schema, Event, and Projection Migration

Status: Accepted
Acceptance date: 2026-08-04

## Context
Relational schemas, immutable event contracts, and disposable projections evolve differently.

## Decision
Use Alembic only for relational schema. Keep permanent upcasters beside contracts. Migrate projections by shadow replay and activation. Deploy expand–migrate–contract with backup/headroom gates. Roll back binaries only if they understand every written contract; otherwise restore the pre-upgrade backup and accept its RPO.

## Alternatives
Rewrite historical events, put upcasters in Alembic, or promise unconditional downgrade.

## Tradeoffs
Compatibility code remains long-lived and releases need explicit rollback declarations.

## Future impact
Every release publishes a compatibility matrix and migration evidence.
