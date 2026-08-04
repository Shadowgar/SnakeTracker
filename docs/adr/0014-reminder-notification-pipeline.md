# ADR-0014: Separate Reminder and Notification Stages

Status: Accepted
Acceptance date: 2026-08-04

## Context
Combining due-state calculation, user intent, queueing, execution, and attempts obscures deduplication and recovery.

## Decision
Separate reminder facts, notification intent, transactional outbox handoff, durable job, delivery attempts, and provider operation. Each has its own stable deduplication boundary. Delivery mechanics are operational, not domain events, unless future business requirements explicitly change that.

## Alternatives
One notification table or direct sends from projection handlers.

## Tradeoffs
More records and state transitions provide clearer recovery and auditability.

## Future impact
New channels implement the same pipeline and declare external duplicate controls.
