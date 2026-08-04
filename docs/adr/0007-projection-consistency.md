# ADR-0007: Classify Projection Consistency

Status: Accepted
Acceptance date: 2026-08-04

## Context
Updating every projection in the command transaction increases latency and lock duration; making everything asynchronous risks incorrect commands and stale access.

## Decision
Authorization, command-invariant, current-state, and inventory projections are synchronous. FTS, reports, expensive dashboard statistics, snapshots, and noncritical analytics are asynchronous. User-facing freshness is exposed where material.

## Alternatives
All synchronous or all asynchronous projections.

## Tradeoffs
Two processing modes increase operational visibility needs. The command path stays correct and small.

## Future impact
Changing consistency class requires measured justification and impact review.
