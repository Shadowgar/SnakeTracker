# M6 password-recovery tranche

This tranche adds only password recovery and its security/delivery boundary before the deferred
fresh-demo reset and final UX overhaul. It does not add Calendar, alter household business events,
merge PR #8, record M6 owner acceptance, or begin M7.

## Architecture and security boundary

Password-reset credentials are ephemeral relational identity/security records under the existing
ADR-0002 rule, not immutable domain events and not M5 husbandry notification intents. Each raw token
contains 384 bits of cryptographic randomness and exists only in the application long enough to build
and deliver a one-time canonical-origin URL. The URL carries the token in a fragment so ordinary HTTP
request targets and access logs never receive it. SQLite stores only the runtime-secret-keyed SHA-256
digest, user scope, request/expiry/consumption/invalidation times, and safe initiation source.

Credentials expire after 45 minutes. A new request invalidates older outstanding credentials for the
same user. Successful reset atomically updates the existing Argon2id password hash, consumes the
presented credential, invalidates all other reset credentials for the user, revokes every active user
session with reason `password_reset`, and records a token-free security audit. The browser requires a
fresh normal sign-in afterward. No user ID, household ID, membership, or role is accepted by the reset
surface.

Public known-account, unknown-account, and throttled requests return the same generic 303 redirect and
confirmation: “If an account exists for that email, password reset instructions have been sent.”
Request throttling uses the existing durable authentication throttle with a keyed normalized-email/IP
key. CSRF, canonical-origin form validation, and the existing 12-to-1024-character password policy
remain in force.

## Delivery and operator recovery

Reset delivery crosses a dedicated identity-message port so a future production email adapter can be
added without changing identity semantics. Delivery is disabled by default. The provided local-file
adapter is rejected in production and is available only under explicit development/test configuration;
it writes no browser-readable route or application log and protects its capture directory/file as
0700/0600. The promoted review configuration derives links from `https://tracker.theroccos.us`.

Trusted self-hosted operators may run
`python -m snaketracker.operations.account_recovery owner@example.com` inside the local application
container. The command accepts no password, creates the same audited one-time credential, and prints
the URL only to the attached terminal. It cannot change household membership or role.

## Data-safety baseline

Before migration, real household `ed44a39b-48ab-5e76-b55e-c0a553dd4030` was at
`0012_account_reminder_inventory`, SQLite integrity was `ok`, and foreign-key violations were zero.
Its 21 domain events, core state, identity, and attachment hashes were respectively:

- `d30fc149221a05a097aa9035fb2f0f4d83e66a64fc28cc62b01bebe5d66472bd`;
- `30ab5beadce4248e3e372b8ca6c1a088adfcc9d57644344005c2ce33c7167af2`;
- `9d1a4036d1b6e657924f9845ee2ed6eaa82249438f414c56cf200d658b4409e2`;
- `1b061498c023525ae3ced752a15b97d69f2433f80486aeab4ecd8cbc70820f38`.

The verified pre-change encrypted backup request
`8bd8e089-7e85-4b60-b5c3-5138cee7b53a` produced run
`3b688ab4-2691-4035-adc7-a51b40d87319` with manifest SHA-256
`06844213d563b862b11f7aaeda1b1c76490d3ed5c9ffb985d9d920e402624a7e`. Its isolated restore
returned `verified` with 14 attachments.

## Automated qualification

- Focused identity, recovery, migration, backup, registration, CSRF, isolation, and operator set:
  83 passed, followed by the changed-backup subset at 13 passed.
- Strict mypy: no issues in 121 source files.
- Ruff formatting and lint: passed.
- Full coverage run: 443 product tests passed; its only initial failure was the not-yet-created evidence
  link checked by the quality-contract test. That quality-contract test passed immediately after this
  evidence path was created. Four added fail-closed coverage tests then passed in their focused set;
  all 448 collected tests are accounted for across the full and post-document/fail-closed runs.
- Final coverage gates: lines 95.08 percent, branches 85.20 percent, combined 93.26 percent.
- Dependency-boundary verification, architecture freeze (41 accepted ADRs), documentation links (188
  files), Compose configuration, and diff checks: passed.
- Exact exported production dependency audit: no known vulnerabilities.

## Promoted browser and security qualification

Native ARM64 Chromium `151.0.7922.173` passed the public-origin journey at 1440-by-1000 desktop and
390-by-844 mobile viewports. The journey created only isolated qualification households and proved:

- known and unknown reset requests use the same generic confirmation;
- explicit local development delivery produces the canonical
  `https://tracker.theroccos.us/reset-password#token=...` URL without a browser listing route;
- the URL fragment is removed after the same-origin static script transfers the token to the form;
- password entry/confirmation and the 12-character minimum are enforced;
- successful reset revokes two pre-existing sessions and requires fresh normal authentication;
- the old password is rejected and the new password is accepted;
- a consumed token and a deliberately expired qualification token both render the same safe invalid
  state;
- initial email and new-password focus, keyboard-usable forms, and horizontal-overflow checks pass;
- seven affected axe scans report zero accessibility violations.

There were zero Care Keeper application JavaScript/runtime console errors, zero page errors, and zero
CSP violations caused by Care Keeper-owned resources. Public HTML contained an inline Cloudflare
`/cdn-cgi/challenge-platform/scripts/jsd/main.js` bootstrap that origin HTML did not contain; Care
Keeper's intentional `script-src 'self'` rejected it, producing 58 external-platform CSP diagnostics.
The three other console diagnostics were the deliberately exercised HTTP 401/400 old-password and
invalid-token responses. Axe used the DevTools evaluation path in this run and produced no additional
harness diagnostic. Production CSP stayed unchanged and contains no Cloudflare allowance,
`unsafe-inline`, or `unsafe-eval`.

All four local delivery artifacts created by qualification were removed after use; the capture
directory is empty. Raw reset tokens and URLs did not enter application logs, audit details, events,
analytics, or the database.

## Final migration, integrity, backup, and runtime

Migration `0013_password_recovery` applied through the existing Compose migration service. Final live
SQLite integrity is `ok` with zero foreign-key violations. The real household's 21 events, projection
counts, and all four pre-change hashes above compare exactly after migration and browser qualification;
the real owner has zero password-reset credential rows and the real password was never changed.

Final encrypted backup request `9ee7e102-1cb8-461f-ab6a-69c0bbd7860d` produced run
`8cd6df2a-4b60-462c-8cb9-efb462e2ef94`, archive
`/var/lib/snaketracker/backups/8cd6df2a4b60462c8cb9efb462e2ef94`, and manifest SHA-256
`4501f9108c34c1c680aaabc859bbd08c253ede68deb22bfcba99cbf7f291abf5`. Its isolated restore returned
`verified` with 14 attachments. Source/restored aggregate counts match at 9 users, 9 households, 310
events, and 14 attachment versions. The restored database is at `0013`, has integrity `ok`, zero FK
violations, zero sessions, and zero password-reset credentials, proving temporary identity credentials
are excluded from backup copies.

The promoted native ARM64 image is `snaketracker:password-recovery`, image ID
`sha256:2b43a9d3b15087ba073e39c7e9d5e10b8ee129d11d6deb32d3b09c220d22dbbf`. Web and worker run as
UID/GID `1001:1001`; web, worker, and nginx health checks pass at the internal and public origin, and
exactly one Care Keeper Compose stack remains active on `127.0.0.1:8081`.

Production email remains intentionally unconfigured. Deployment must provide a production-safe email
adapter for the identity-message port; the local-file adapter is hard-rejected in production and is
enabled only for this explicit development owner-review configuration.
