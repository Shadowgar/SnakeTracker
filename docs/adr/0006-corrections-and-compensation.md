# ADR-0006: Correct History with New Events

Status: Accepted
Acceptance date: 2026-08-04

## Context
Immutable history must coexist with human error, reversal, privacy procedures, and cross-stream effects.

## Decision
Corrections, voids, reinstatements, and compensations append new typed events. Registrations declare capabilities, roles, age policies, and reversal behavior. Cross-stream effects require explicit compensating events. Privacy redaction retains a non-sensitive structural tombstone.

## Alternatives
Mutate payloads in place, hard-delete events, or hide errors only in the UI.

## Tradeoffs
Effective-state projections and correction chains are more complex, but auditability and replay remain trustworthy.

## Future impact
Every new material event contract must define correction semantics before registration.
