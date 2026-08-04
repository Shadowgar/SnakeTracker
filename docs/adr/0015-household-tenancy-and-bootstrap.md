# ADR-0015: Use Household-Scoped Multi-User Tenancy

Status: Accepted
Acceptance date: 2026-08-04

## Context
V1 needs multiple users in one household and a future organization seam.

## Decision
Every owned event and record carries household scope. Household creation and initial owner events plus authorization projection commit atomically. Every protected request checks the current authorization projection; session claims alone do not authorize.

## Alternatives
Single-user v1 or full organizations from day one.

## Tradeoffs
Tenant scoping adds pervasive tests but avoids later ownership redesign without premature SaaS complexity.

## Future impact
Organizations may generalize household ownership through a dedicated migration ADR.
