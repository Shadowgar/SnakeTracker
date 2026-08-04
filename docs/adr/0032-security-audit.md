# ADR-0032: Maintain a Separate Security Audit Facility

Status: Accepted
Acceptance date: 2026-08-04

## Context
Authentication, denied access, backups, plugins, and exports are security operations rather than business-domain facts.

## Decision
Use conventional append-oriented relational audit records for authentication, sessions, permissions, sensitive access/export, backup/restore, plugins, redaction, and denied access. Store safe UTC context and correlation, never secrets or payload bodies. Prevent application-user mutation and control retention/export.

## Alternatives
Domain events, ordinary logs only, or mutable administrator notes.

## Tradeoffs
Audit storage and privacy governance are required; append orientation is not itself cryptographic tamper evidence.

## Future impact
Tamper evidence requires separate HMAC/hash-chain key design.
