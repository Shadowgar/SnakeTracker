# ADR-0016: Use Server-Side Secure Sessions

Status: Accepted
Acceptance date: 2026-08-04

## Context
The HTML-first application needs secure revocable authentication with future OAuth/MFA support.

## Decision
Use Argon2id password hashes and opaque tokens whose hashes are stored server-side. Apply secure cookie attributes, CSRF, rotation, idle/absolute expiry, rate limiting, hashed single-use recovery/invitation tokens, and recent-auth checks for high-risk actions.

## Alternatives
Stateless browser JWTs or external identity as a mandatory v1 dependency.

## Tradeoffs
Sessions require relational storage and cleanup but enable immediate revocation.

## Future impact
OAuth and MFA attach to identity without changing household authorization.
