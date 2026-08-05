# AT-AUD-01 Security Audit and CSRF Evidence

- Requirements: R-024, R-033
- ADRs: ADR-0023, ADR-0032
- Threat controls: TM-03, TM-16, TM-17
- Result: Pass for local M2 scope

Security audit rows are conventional operational records, separate from domain events. Bootstrap,
successful and failed login, logout, denied protected requests, and restoration-driven session
invalidation append categorized outcomes with correlation IDs and bounded technical context.
Passwords, raw session tokens, raw CSRF tokens, and plaintext secrets are never recorded.

Browser tests verify synchronized CSRF tokens, `SameSite=Strict`, supported form content types,
same-origin rejection even with a valid token, CSRF failure pages, login throttling, strict CSP, and
safe response headers. Trusted proxy and remote/public origin controls remain deferred and do not
receive M2 approval.
