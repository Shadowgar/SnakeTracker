# SnakeTracker Threat Model

## Scope and trust assumptions

Protected assets include credentials, sessions, household membership, animal and health records, notes, financial records, attachments, event history, backups, plugin packages, encryption keys, and administrative operations.

The Pi host administrator, Docker host, and independently managed backup-key custodian are trusted. Browsers, uploaded content, network inputs, external providers, and plugin packages before verification are untrusted. Installed trusted plugins are privileged and not sandboxed.

## Trust boundaries

1. Public client to Cloudflare edge
2. Cloudflare/cloudflared to Nginx
3. Nginx to FastAPI
4. Presentation to application authorization
5. Application to event/operational database
6. Application to attachment storage
7. Worker to external providers
8. Worker to backup repository and independent key management
9. Core application to trusted plugin code

## Threats and required controls

| ID | Threat | Required controls | Class |
|---|---|---|---|
| TM-01 | Credential guessing or stuffing | Argon2id, rate limits, generic failures, audit, future MFA seam | RD |
| TM-02 | Session theft or fixation | Opaque hashed sessions, secure cookies, rotation, idle/absolute expiry, revocation | RD |
| TM-03 | CSRF | Tokens, SameSite cookies, origin/content-type checks | RB/RD |
| TM-04 | Cross-household disclosure or mutation | Current authorization projection, household scope, object ownership tests, fail closed | RB |
| TM-05 | Stored/reflected XSS | Autoescaping, strict CSP, Alpine CSP build, external scripts, sanitization | RB/RD |
| TM-06 | Malicious upload or parser bomb | Type/signature allow-list, size/dimension/decompression limits, isolated processing | RB/RD |
| TM-07 | Active attachment execution | Reject or download active content, safe headers, non-executable storage, controlled endpoint/origin | RB/RD |
| TM-08 | Forwarded-header spoofing | Trusted-hop allow-list, header replacement, host allow-list, direct-access blocking | RD |
| TM-09 | Event/history corruption | Transactions, checksums, integrity checks, verified backups, replay tests | RB |
| TM-10 | Malicious history alteration | Append-only application policy, capabilities, security audit; optional future tamper evidence | RB/DC |
| TM-11 | Duplicate external effects | Provider idempotency, durable external IDs, reconciliation, bounded tolerance | RB where used |
| TM-12 | Backup disclosure | Encryption, independent keys, no plaintext secrets, controlled access, audit | RD |
| TM-13 | Unrecoverable backup | Verification, retention, off-device copy, restore tests, key-recovery drills | RB/RD |
| TM-14 | Dependency or image compromise | Locked dependencies, SBOM, scanning, signed artifacts, pinned images | RD |
| TM-15 | Malicious/incompatible plugin | Signature/source trust, compatibility scan, explicit capabilities, safe startup | RB when plugins enabled |
| TM-16 | Privilege abuse | Capability separation, recent-auth checks, audit, least privilege | RD |
| TM-17 | Sensitive log leakage | Structured allow-listed logging and redaction tests | RB/RD |
| TM-18 | Denial of service/storage exhaustion | Limits, quotas, free-space gates, resource limits, backpressure | RD/QT |
| TM-19 | Unsafe offline persistence | Deny-by-default drafts, low-sensitivity allow-list, expiry and clearing | RB |
| TM-20 | Incompatible newer data opened by older code | Read-only compatibility scan and restricted recovery mode | RB |

## Abuse cases

- A viewer changes an animal UUID in a request: authorization must deny before data is returned or changed and record the denial.
- An attacker supplies `X-Forwarded-For` directly: Nginx discards it and FastAPI trusts only Nginx-generated forwarding data.
- A user uploads an SVG with script: it is rejected or forced to download from a non-executable origin.
- A plugin is removed after writing events: compatibility scan prevents normal startup until handlers return.
- A worker sends email and crashes before completion: provider idempotency or reconciliation prevents uncontrolled duplication.
- A stolen backup is obtained without the independent key: its contents remain confidential.

## Review cadence

Review at every milestone, before remote deployment, whenever a trust boundary changes, and for every new plugin or external provider. Findings and evidence belong under the relevant `/docs/evidence/<milestone>/security` directory.
