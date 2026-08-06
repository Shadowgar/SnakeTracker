# M2 Security Boundary Evidence

- Execution date: 2026-08-06
- Implementation revision: `25d52a34ce3cb343d1678de75118863d844d80b5`
- Architecture baseline: `6c6ae1fa9a1690ab30d453666aecee3eae0acffb`
- Branch: `phase2/identity-household`
- Environment: x86_64 WSL2 laptop, Docker Engine, Python 3.13.14
- Operator: Codex automation in `/home/rocco/SnakeTracker`
- Milestone status: **implementation qualified; owner acceptance pending**

## Outcome

All applicable M2 release-blocker checks pass locally. The implementation provides the permanent
household event slice authorized by ADR-0037, atomic first-owner bootstrap, Argon2id credentials,
household-bound opaque sessions, current-membership authorization, CSRF and same-origin controls,
durable login throttling, append-oriented security audit records, and the browser-visible setup,
login, home, and logout flows.

The remote-deployment criterion remains unchecked. Trusted-proxy, public-host, TLS-origin, and
other remote-access controls are still deferred; this evidence does not approve public deployment.
M2 is not accepted until the owner reviews this branch. Phase 3 has not started.

## Inventory

- [Quality and test evidence](tests/README.md)
- [Household bootstrap evidence](tests/bootstrap.md)
- [Authentication evidence](security/authentication.md)
- [Authorization evidence](security/authorization.md)
- [Security-audit evidence](security/audit.md)
- [Container and ARM64 evidence](containers/README.md)
- [Browser and accessibility evidence](browser/README.md)
- [Mobile authenticated-home screenshot](browser/mobile-home.png)
- [PR #3 automated-review disposition](reviews/pr-3-review-disposition.md)

## Reproduction

Run the quality gate from the repository root:

```sh
uv sync --frozen
./scripts/quality/check.sh
```

Start the current owner-facing laptop stack on port 18081. The retained initial container and
browser evidence used 8081; Windows/Hyper-V subsequently reserved that port. Port 8080 is owned by
another local project:

```sh
SNAKETRACKER_UID=1001 COMPOSE_BAKE=false docker compose build web
SNAKETRACKER_DATA_DIR=./runtime/phase2 \
SNAKETRACKER_BIND_ADDRESS=0.0.0.0 \
SNAKETRACKER_HTTP_PORT=18081 \
SNAKETRACKER_EXTERNAL_ORIGIN=http://localhost:18081 \
docker compose up -d --no-build
```

The `0.0.0.0` bind is required for Windows-to-WSL2 localhost forwarding in the qualified laptop
topology; the Compose default remains the local-only `127.0.0.1`. Windows Firewall remains the
host boundary. Open `http://localhost:18081/setup` from Windows. The active qualification database
is intentionally fresh and shows the first-run setup page.
