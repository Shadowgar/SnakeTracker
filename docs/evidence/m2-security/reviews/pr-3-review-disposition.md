# PR #3 Automated Review Disposition

- Review date: 2026-08-06
- Corrected implementation revision: `25d52a34ce3cb343d1678de75118863d844d80b5`
- Reviewers and checks: CodeRabbit, GitHub Copilot, GitHub Actions Quality and Container,
  GitGuardian
- Reviewer: Codex technical verification; owner approval remains the M2 acceptance gate

## Required corrections

| Finding | Resolution and evidence |
|---|---|
| Stored household payloads were coerced instead of validated | Registry now requires exact field types and the literal `owner` role; malformed-payload tests fail closed. |
| Replay did not compare envelope household identity with its stream | Replay rejects mismatched household and stream identities. |
| A missing CSRF cookie left an authenticated user unable to log out | `/home` rotates the server-side session and reissues both cookies; the old session is revoked and the browser regression completes logout. |
| Broad `ValueError` handling could expose internal adapter details | A dedicated `BootstrapValidationError` is the only domain-validation exception rendered as a form error. |
| Audit timestamps used wall-clock time inside the repository | Every audit write receives the operation timestamp; deterministic microsecond-level assertions cover denial and login failure. |
| Absolute-expiry and rate-limit tests were ambiguous | Absolute expiry is isolated from idle expiry, and every failed-login response is asserted as `401, 401, 401, 401, 401, 429`. |
| Security-test engines could leak after failures | The typed yield fixture disposes the SQLAlchemy engine in `finally`. |
| Migration tests counted foreign keys but did not verify targets | Tests assert exact referenced tables. A forward Alembic revision removes the redundant stream index without rewriting an already-applied migration. |
| Dependency-scope parsing missed valid requirement syntax | The architecture test uses `packaging.Requirement` and canonical package names; `packaging` is a locked direct development dependency. |
| Disabled browser routes were silent | Startup emits a warning for a missing runtime secret or incompatible stored data, with a regression test. |
| Setup errors lacked complete accessible relationships | Error keys are guarded; field messages have stable IDs, `aria-describedby`, and alert semantics. |
| CSS failed Stylelint declaration grouping | The custom-property group is separated from the ordinary declaration. |
| Documentation and evidence had stale phase, cookie, endpoint, count, provenance, and ARM64 labels | Records now say Phase 4, SameSite=Strict, distinguish historical 8081 from current 18081, record 132 tests, include bootstrap provenance, pin Pa11y 9.0.1, and label ARM64 as emulated with native Pi deferred. |
| Phase 2 implementation checklist remained visually open | Completed implementation and qualification tasks are checked; milestone acceptance remains separately governed. |

Reproduce the corrected local gate with:

```sh
uv sync --frozen
./scripts/quality/check.sh
```

## Valid but deferred

No substantive automated-review finding was deferred. The already-classified remote/public
deployment gate and native Raspberry Pi qualification remain deferred requirements, not newly
discovered review defects.

## False positives

| Finding | Supporting evidence |
|---|---|
| The documented Compose `up --no-build` command supposedly needed `SNAKETRACKER_UID` | `compose.yaml` consumes `SNAKETRACKER_UID` only as a Docker build argument. The separately documented `up --no-build` operation does not build and therefore cannot consume it. |
| Reduced-motion CSS should be removed because the current page has no animation | The rule intentionally satisfies the accepted accessibility baseline and prevents future smooth scrolling from overriding a user preference. It has no adverse current behavior. |
| CodeRabbit's generic 80% docstring-coverage target | SnakeTracker's accepted gate is behavioral line/branch coverage plus lint, typing, architecture, documentation, and dependency checks. No ADR or project configuration defines docstring coverage, and adding low-value docstrings solely for an external default would not improve correctness. |

Quality, Container, and GitGuardian were green before corrections and reported no additional
substantive findings. Their final post-correction states are retained by PR #3.
