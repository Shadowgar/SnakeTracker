# Security Architecture

## Identity and sessions

Passwords use Argon2id with versioned parameters benchmarked on the Pi. Successful authentication may transparently upgrade weaker stored hashes. Sessions use opaque high-entropy tokens with only token hashes stored server-side. Cookies are Secure, HttpOnly, SameSite, narrowly scoped, and rotated after authentication and privilege changes. Idle and absolute limits apply. Logout, role loss, password reset, restoration, and administrator action can revoke sessions.

Password-reset credentials contain 384 bits of cryptographic randomness, expire after 45 minutes,
are scoped to one user, and are stored only as runtime-secret-keyed SHA-256 digests in mutable
identity/security storage. A new request supersedes older credentials. Successful reset atomically
updates the Argon2id password, consumes the credential, invalidates every other reset credential for
the user, and revokes every authenticated session; normal sign-in is then required. Reset credentials
are operational security state, never domain events. Invitation secrets follow the same
single-use/short-lived rule when that deferred capability is implemented. OAuth and MFA are deferred
but must attach to the same identity and household-capability model.

Unauthenticated reset requests always use the same response, status, and redirect for known, unknown,
and throttled addresses. Reset URLs use only the configured canonical external origin. Their raw token
is carried in a URL fragment so it is not sent in HTTP request targets or ordinary access logs; a
same-origin static script transfers it to the reset form and removes the fragment. Passwords, password
hashes, raw reset tokens, and reset URLs are excluded from application logs, audit details, analytics,
and events.

## Authorization

Roles are Owner, Administrator, Caretaker, and Viewer, implemented as explicit capabilities. Every protected request checks current membership, capability, household, and subject ownership against the synchronous authorization projection. Session claims are not sufficient. Sensitive exports, health/financial data, users, plugins, backup, restore, and redaction use distinct capabilities. High-risk operations may require recent authentication.

## Browser and API security

Browser writes require CSRF tokens, trusted origin, and expected content type. Templates autoescape. The frontend uses Alpine's CSP build and external versioned scripts; generated JavaScript in templates, `unsafe-inline`, and `unsafe-eval` are prohibited. Security headers include strict CSP, HSTS at the public boundary, frame denial, MIME sniffing prevention, controlled referrer policy, and permission restrictions.

API inputs and outputs use explicit schemas. Errors expose correlation identifiers without secrets. Rate limits apply to authentication, invitations, exports, uploads, and expensive queries. ETag/If-Match and explicit stream-version rules prevent lost updates.

## Proxy security

Only the configured Cloudflare Tunnel path reaches Nginx. Nginx removes client-provided forwarding headers and emits canonical forwarding values. FastAPI trusts only the known Nginx service network. Hostnames are allow-listed, secure URL generation uses validated external-origin configuration, and direct public ports are closed. Tests cover spoofed IPs, hosts, schemes, and redirects.

## Attachments

Staged uploads are isolated and non-executable. Validation covers file signature, type, size, expanded size, pixel count, dimensions, archive depth, and decompression ratio. Finalized storage keys are random and immutable. Active content is rejected by default. Authorized media delivery applies safe type, disposition, nosniff, cache, and CSP headers. Original names never become filesystem paths.

## Security audit

An append-oriented relational audit records authentication, password-reset initiation/completion,
session revocation, permission, denied-access, export, backup, restore, plugin, redaction, and
security-setting activity. Audit data contains safe context but no credentials, tokens, reset URLs,
or protected payload bodies. Users cannot edit it. Access and export are capability controlled.

## Secrets and backups

Secrets are injected at deployment and never baked into images or source. Backups retain password hashes but exclude or invalidate sessions and temporary credentials. Plaintext application secrets and backup decryption keys never enter a backup set. Keys are independently managed, rotated, and recovery-tested.

## Supply chain and plugins

Dependencies are pinned, scanned, and represented in an SBOM. Release images use pinned digests and signed artifacts. Plugins are verified trusted packages with explicit API and contract compatibility. They are not sandboxed. Missing or incompatible handlers force restricted recovery mode.

## Security acceptance

Before remote/public deployment, all RD items in the traceability matrix require reproduced evidence: proxy tests, CSP regression, cross-household authorization, session and CSRF tests, upload adversarial tests, backup confidentiality/recovery, dependency scan, and administrative audit verification.
