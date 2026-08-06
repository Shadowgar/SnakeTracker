# AT-AUTHZ-02 Authorization Evidence

- Requirement: R-016
- ADR: ADR-0015
- Threat controls: TM-04, TM-16
- Result: Pass

Every `/home` request resolves the hashed session against the session-bound household, active user,
current synchronous membership projection, and current role. A suspended membership, disabled
user, expired/revoked session, or session whose household has no matching membership fails closed.

`tests/security/test_identity_security.py` verifies household binding, cross-household rejection,
membership suspension, and role-capability recalculation. `tests/browser/test_identity_flow.py`
verifies unauthenticated redirection and a usable authenticated home page.
