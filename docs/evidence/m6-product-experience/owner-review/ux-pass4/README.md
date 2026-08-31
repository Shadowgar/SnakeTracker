# M6 UX Overhaul Pass 4 — Secondary Experience and Auth/Onboarding

Status: **deployed for owner visual review; not owner-accepted**

Qualification date: 2026-08-31. Branch: `phase6/product-experience`. Owner-review origin:
`https://tracker.theroccos.us`. This pass completes the major secondary-screen UX implementation
for Inventory, Expenses, Reports, More internals, authentication, onboarding, Search, Backups, and
System Operations. It does not perform final M6 acceptance or release qualification, merge PR #8,
or begin M7/M8.

## Product result

- **Inventory** now leads with active, attention, tracked, and archived summaries. Dense responsive
  supply cards expose remaining, reserved, consumed, and configured reorder-threshold quantities.
  Detail, edit, receive, adjust, archive, and restore are focused flows; immutable stock history and
  archived-item feeding exclusion semantics are unchanged.
- **Expenses** now separates effective summaries from the record stream. Current-month, rolling
  30-day, and all-active totals exclude voided expenses and never combine currencies into a false
  single total. Category totals, friendly dates/currency, merchant/context, and explicit void state
  remain readable on phone and desktop.
- **Reports** now has collection, care, and expense overview cards backed by existing read models.
  Detail reports use a dense desktop table and labelled stacked mobile rows, retain textual content,
  and preserve all existing CSV exports and CSV-injection protection.
- **Reminders** presents compact schedule rows with animal context, cadence, next due state, and a
  link into the existing focused animal schedule editor. Reminder reconciliation and due semantics
  are unchanged.
- **Search** adds result-type markers and animal photography/context where supported without
  changing FTS semantics. More retains the accepted compact grouping while clarifying the account,
  collection setup, Backup, and System destinations.
- **Authentication** uses a focused Care Keeper shell for sign in, account registration, forgot
  password, reset password, and reset-result states. Existing registration isolation and all
  password-reset security behavior remain unchanged.
- **Onboarding** is state-derived, skippable, and resumable. Registration creates the household once,
  then the flow points to existing animal, enclosure, assignment, and schedule commands. It never
  creates husbandry defaults or traps a user in a rigid wizard.

Empty Inventory, Expenses, Reports, Reminders, Animals, and onboarding states provide a useful next
action. Backups remain under Advanced and keep restore operator-controlled. System Operations is
explicitly technical and remains outside primary mobile navigation.

## Browser, responsive, accessibility, and console qualification

Native ARM64 `Chrome/151.0.7922.173` exercised the deployed public origin at 390×844, 360×800,
1440×900, 1023×800, and 1024×800. The 1023px shell remains mobile and the 1024px shell desktop.
There is no horizontal overflow, no same-origin HTTP failure, no Care Keeper JavaScript/runtime
console finding, and no page error. All 20 screenshot routes passed axe WCAG 2.2 A/AA with zero
violations. Responsive report rows expose their labels on mobile rather than squeezing a desktop
table. Form labels, focus states, landmarks, status text, and touch targets remain accessible.

Machine-readable evidence is in [`qualification.json`](qualification.json) and
[`console.json`](console.json). The strict-CSP scan found zero violations associated with a
Care Keeper-owned resource. Care Keeper templates emit only same-origin external scripts. The
public Cloudflare edge injects an inline analytics/browser-insights loader and a
`static.cloudflareinsights.com` beacon; the unchanged `script-src 'self'` policy intentionally
rejects both. CSP diagnostics produced while axe injects its script are qualification-instrument
artifacts. No Cloudflare allowlist, `unsafe-inline`, `unsafe-eval`, nonce, hash, or other CSP
relaxation was added.

## Owner-review screenshots

Mobile 390×844:

- [Inventory](mobile-inventory.png)
- [Focused inventory adjustment](mobile-inventory-adjust.png)
- [Expenses](mobile-expenses.png)
- [Reports landing](mobile-reports.png)
- [Collection report](mobile-report-collection.png)
- [Care-history report](mobile-report-care.png)
- [Search results](mobile-search.png)
- [Sign in](mobile-sign-in.png)
- [Register](mobile-register.png)
- [Forgot password](mobile-forgot-password.png)
- [Empty-household onboarding](mobile-onboarding.png)
- [More and Advanced organization](mobile-more-advanced.png)

Desktop 1440×900:

- [Inventory](desktop-inventory.png)
- [Expenses](desktop-expenses.png)
- [Reports landing](desktop-reports.png)
- [Collection report](desktop-report-collection.png)
- [Search results](desktop-search.png)
- [Sign in and auth shell](desktop-sign-in.png)
- [Empty-household onboarding](desktop-onboarding.png)
- [Advanced System Operations](desktop-system.png)

The onboarding captures use a temporary isolated self-service qualification account on the same
deployed public environment. That household contains no animals, enclosures, inventory, expenses,
or schedules and cannot access the fictional demo or owner-created household. No owner household
record was used or mutated for the flow.

## Authoritative quality gate and promoted runtime

The frozen project environment completed `uv sync --frozen`, followed by the unchanged
`./scripts/quality/check.sh` authoritative gate (with the established 120-second per-test timeout).
Formatting, Ruff, the architecture freeze, documentation links, strict mypy, all 460 tests,
coverage artifacts, dependency audit, Compose validation, and repository diff checks passed.
Pytest completed in 562.04 seconds with 94.81% line and 85.14% branch coverage; the dependency audit
reported no known vulnerabilities.

The promoted native ARM64 application image is
`sha256:781c1256c38a0ac1064561d43f0f15dbe5a0cdb04b357911a9cbdd4ec93eb76b`.
The single `snaketracker` Compose project has one healthy web, worker, and nginx service. Web and
worker run as UID/GID `1001:1001`; local liveness/readiness and the public sign-in origin respond
successfully. The final read-only SQLite checks report `integrity_check=ok`, zero foreign-key
violations, and migration head `0013_password_recovery`.

## Scope and production boundary

No migration, event contract, inventory/accounting policy, report event, reminder rule, CSP, or
household-authorization semantic changed. Migration head remains `0013_password_recovery`.
The fictional fixture remains 20 animals, 16 enclosures, 506 events, and 21 attachment versions;
the owner-created household remains one animal, one enclosure, five events, and zero attachments.
The deterministic green-dot fictional attachments remain the known visual limitation and were not
regenerated.

The saved pre-pass fixture count was 505 events. During the qualification window, an independent
interactive Microsoft Edge session submitted one feeding-schedule command against a fictional demo
animal at `2026-08-31T04:41:07Z`; nginx access evidence distinguishes that Windows/Edge request from
the Linux ARM64 Chromium qualification. Care Keeper appended the valid `reminder.rule_created`
event, bringing the demo count to 506. This pass did not submit, remove, or rewrite that event. The
owner-created household stayed exactly unchanged.

Password recovery continues to cross the dedicated identity-message port. The local-file adapter
is appropriate only for this development owner-review environment and production startup rejects
it. Release deployment still requires a production email adapter that keeps reset URLs out of
analytics and ordinary logs; no commercial provider or credentials were introduced in this pass.

## Stop boundary

Automated qualification is not owner visual acceptance. Final M6 owner-review corrections (if
requested), final M6 qualification, PR #8 review readiness/merge, M7, and M8 all require explicit
future direction.
