# AT-AUTHN-01 Authentication Evidence

- Requirement: R-017
- ADR: ADR-0016
- Threat controls: TM-01, TM-02, TM-03
- Result: Pass for enabled M2 identity flows

`tests/security/test_identity_security.py` verifies Argon2id password hashes, generic login
failures, durable per-principal/client throttling, opaque HMAC-hashed session and CSRF tokens,
session rotation, idle and absolute expiry, logout revocation, current-user status, and bulk session
invalidation after restoration. Cookies are `HttpOnly`, `SameSite=Strict`, path-scoped, and use the
configured Secure policy. The local HTTP Compose profile explicitly disables Secure cookies; the
production configuration continues to require HTTPS and Secure cookies.

Password recovery and invitations are not enabled in the initial-owner-only M2 interface; no
recovery or invitation token is issued or accepted. Their hashed single-use implementation remains
required before those workflows can be enabled.
