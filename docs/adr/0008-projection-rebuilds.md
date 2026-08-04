# ADR-0008: Use Versioned Projection Generations

Status: Accepted
Acceptance date: 2026-08-04

## Context
Projection upgrades and recovery must not destroy the last usable read model.

## Decision
Build generation-specific shadow tables/views/FTS structures, replay to a high-water point, validate, catch up, and atomically publish the active generation. Interdependent projections swap as one group; old generations remain for rollback and later resumable cleanup.

## Alternatives
Truncate/rebuild in place or ad hoc table replacement.

## Tradeoffs
Temporary storage headroom and generation-aware repositories are required.

## Future impact
Integration tests must cover swap, rollback, interruption, foreign keys, views, FTS, and cleanup.
