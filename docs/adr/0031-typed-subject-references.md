# ADR-0031: Validate Typed Subject References

Status: Accepted
Acceptance date: 2026-08-04

## Context
Requiring an animal UUID on every event cannot represent enclosure, household, inventory, expense, and document events honestly.

## Decision
Use registered typed references containing subject type, UUID, relationship role, and optional order. Contracts declare required roles. Append validation proves type registration, existence, same-household ownership, and actor permission through the responsible resolver.

## Alternatives
Animal-only foreign key or unrestricted JSON references.

## Tradeoffs
Validation may touch multiple repositories and must remain inside short transactions.

## Future impact
Plugins register subject resolvers through the public plugin API.
