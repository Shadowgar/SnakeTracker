# ADR-0001: Use a Modular Monolith

Status: Accepted
Acceptance date: 2026-08-04

## Context
SnakeTracker must be maintainable and extensible while running efficiently on one Raspberry Pi.

## Decision
Build one deployable FastAPI application organized into bounded contexts with inward dependencies. Run a separate worker process from the same codebase. The startup package is the sole composition root; infrastructure implements application/domain-owned ports.

## Alternatives
Microservices add network, deployment, consistency, and memory cost. An unstructured monolith makes boundaries unenforceable.

## Tradeoffs
Module discipline must be tested because process boundaries do not enforce it. Independent scaling is deferred.

## Future impact
Contexts may be extracted only after measured need and a superseding ADR.
