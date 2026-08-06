# Phase 2 Identity and Household Implementation Checklist

> **For Codex:** REQUIRED SUB-SKILLS: use `superpowers:test-driven-development` for every behavior,
> `security-best-practices` for the FastAPI/Jinja boundary, and `playwright` for browser evidence.

**Goal:** Deliver a Docker-hosted first-run household/owner bootstrap, secure login/session flow,
current household authorization, and accessible authenticated home page without Phase 3 animal
scope.

**Architecture:** Keep credentials, sessions, rate limits, and security audit relational. Store
household creation and initial owner membership as the permanent ADR-0037 event slice and update
synchronous authorization projections in the same SQLite transaction. Compose everything only in
the FastAPI startup layer.

**Tech stack:** Python 3.13, FastAPI, synchronous SQLAlchemy/SQLite, Alembic, Argon2id, Jinja2,
plain external CSS, Docker Compose, pytest, and Playwright CLI.

**Status:** Implementation and qualification checklist completed and M2 accepted August 6, 2026.

## Ordered test-driven checklist

- [x] Add locked runtime dependencies (`argon2-cffi`, `jinja2`, `python-multipart`) and retain the
  existing quality/coverage gates.
- [x] Add migration `0002_identity_household` for users, event streams/events, idempotency,
  household summary, authorization memberships, sessions, login rate limits, and security audit;
  prove upgrade, downgrade, constraints, and absence of excluded tables.
- [x] Define typed `household.created` and `household.owner_added` v1 contracts, the compatible
  minimal envelope, checksum, registry lookup, replay, and unknown-contract failure.
- [x] Implement one-transaction bootstrap with canonical idempotency hashing, contiguous stream
  versions, credential creation, both events, stored result, and synchronous projections; prove
  rollback and retry behavior.
- [x] Implement Argon2id password hashing/verification and generic validation failures without
  persisting or logging plaintext credentials.
- [x] Implement opaque server-side sessions with hashed tokens, rotation on login, idle/absolute
  expiry, revocation, logout, conditional Secure cookie, HttpOnly, SameSite=Strict, and safe cleanup.
- [x] Implement CSRF synchronizer tokens plus Origin/content-type validation for all browser writes.
- [x] Implement bounded failed-login rate limiting and append-oriented authentication/session/
  authorization/denial security audit records.
- [x] Implement centralized current-membership/capability dependencies; prove that stale session
  identity alone never authorizes and cross-household access fails closed.
- [x] Implement `/setup`, `/login`, `/`, and `/logout` server-rendered routes with autoescaped Jinja,
  strict CSP/security headers, generic usable errors, responsive external CSS, semantic landmarks,
  visible focus, 44px targets, error summaries, and reduced-motion support.
- [x] Run unit, domain, integration, security, migration, browser, and accessibility checks; run the
  exact fresh-install/setup/login/home/protected/logout/relogin/expiry/revocation/rate-limit/CSRF
  Docker flow and retain evidence under `/docs/evidence/m2-security`.
- [x] Mark only verified M2 RB criteria with evidence. Leave trusted-proxy RD and all M3+ criteria
  unchecked; record owner acceptance only after the final review passes.

## Commit sequence

1. `build: add Phase 2 identity dependencies`
2. `feat: add identity and household persistence`
3. `feat: add atomic household bootstrap events`
4. `feat: add secure sessions and authorization`
5. `feat: add accessible identity web experience`
6. `test: qualify Phase 2 identity security flows`
7. `docs: record Phase 2 qualification evidence`

Stop before Phase 3 and do not merge the Phase 2 pull request.
