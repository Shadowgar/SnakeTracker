# ADR-0005: Use Registered Typed Event Contracts

Status: Accepted
Acceptance date: 2026-08-04

## Context
Unstructured JSON metadata would weaken validation, replay, reporting, and plugin safety.

## Decision
`event_id` uniquely identifies a stored event. `event_type + schema_version` identifies its contract. Each registration supplies schema, handlers, authorization, subjects, correction capabilities, renderers, ownership, and upcasters. Upcasters and historical fixtures live beside contracts as permanent runtime code.

## Alternatives
One generic unversioned payload, ORM inheritance tables, or rewriting historical events on every upgrade.

## Tradeoffs
Registrations add ceremony and permanent compatibility responsibility.

## Future impact
Unknown contracts force restricted recovery mode; plugins cannot be removed while their handlers are required.
