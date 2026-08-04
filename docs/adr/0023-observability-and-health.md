# ADR-0023: Separate Health, Metrics, Logs, and Audit

Status: Accepted
Acceptance date: 2026-08-04

## Context
Operators need proof of service health without exposing sensitive diagnostics or conflating logs with audit history.

## Decision
Provide narrow liveness, compatibility-aware readiness, and authenticated administrative diagnostics. Use structured redacted logs with correlation IDs, metrics for latency/lag/jobs/WAL/storage/backups, and a separate security audit facility.

## Alternatives
One public health endpoint or log-only operations.

## Tradeoffs
Instrumentation and access controls add work but make recovery evidence-based.

## Future impact
External monitoring adapters consume stable metrics without changing domain code.
