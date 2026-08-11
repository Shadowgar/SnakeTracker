# M5.5 Security Qualification

Result: **Pass** at revision `fe4a476`.

- Capability enforcement is server-side at application/domain/reminder boundaries; hidden controls
  are not the authorization mechanism.
- Direct inapplicable care requests return stable errors and append no events.
- Unknown projected capability versions fail closed.
- Subject existence, household ownership, current membership/permission, CSRF, session, upload,
  and security-audit controls remain covered by the full suite.
- Attachment storage and delivery remain unchanged from accepted M4 hardening.

Reproduce with `uv run pytest -q tests/security tests/integration/test_multispecies_animals.py
tests/integration/test_profile_photos.py` and `./scripts/quality/check.sh`.

