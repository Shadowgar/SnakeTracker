# ADR-0024: Qualify Performance on a Versioned Pi Environment

Status: Accepted
Acceptance date: 2026-08-04

## Context
Generic performance claims are not reproducible and storage ratios vary with payload distribution.

## Decision
Pin hardware, OS image, filesystem, SSD class, runtime, SQLite build, containers, encryption, dataset distribution, cache state, and concurrency. Treat latency, resource, database, FTS, attachment, WAL, backup, and rebuild budgets as qualification targets for that versioned environment—not universal guarantees.

## Alternatives
Developer-laptop benchmarks or undocumented best-effort performance.

## Tradeoffs
Hardware qualification costs time and must be repeated after material changes.

## Future impact
Two consecutive misses require remediation or a superseding budget ADR.
