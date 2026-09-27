# Platform Administration and Support Console (OPS-A)

## Authority and grant

A household `owner` manages one household. That role does not authorize `/admin`. A platform operator is an existing active Care Keeper account whose canonical user UUID is listed in the **web process** deployment setting `SNAKETRACKER_PLATFORM_OPERATOR_USER_IDS`. The setting grants `platform.admin.read`, `platform.support.read`, and `platform.system.read` together. The default empty setting denies everyone. Normal signup, household settings, and household role changes cannot alter this list.

To grant the initial operator, a trusted person with deployment access:

1. Identifies the operator's existing account UUID from a trusted local account record or registration audit. Verify the account email out of band. Do not use a household ID.
2. Sets `SNAKETRACKER_PLATFORM_OPERATOR_USER_IDS=<canonical-user-uuid>` in the deployment environment, or in the Compose `.env` file accessible only to deployment administrators. Multiple UUIDs can be comma separated; the maximum is ten. The Compose configuration passes this value only to the web service.
3. Recreates the web service with the approved deployment procedure, then signs in normally as that account and opens `/admin`. Confirm `admin.overview.view` appears in `/admin/audit`.

To revoke, remove the UUID and recreate the web service. A deployment restart is needed because authorization is loaded at process start. Disabling an account or revoking its sessions also prevents access because `/admin` requires a currently valid authenticated session. Keep the deployment environment and its change history restricted. Never put an operator UUID into signup input, a browser URL, or a household setting.

## Read-only V1 boundary

The console shows account identity and status, membership, safe session metadata, household collections, keeper-visible effective Animal care, technical event provenance, Inventory consumption links, jobs, backup run metadata, attachment and reference-image file presence, projection status, and audited operator reads. It deliberately crosses household boundaries. Every `/admin` route checks the operator allowlist after validating the session and writes a minimal success or denial record to `security_audit`. Search terms, event payloads, notes, cookies, password hashes, reset tokens, and secrets are never copied into that audit record. Admin responses disable caching.

Normal household routes keep their existing tenancy checks. Operator access does not create an impersonated session and does not extend household route privileges. The Event inspector displays typed relationships and selected envelope fields; it never exposes a raw SQL console or editable event payload. Free-form household notes and expense notes are excluded from list and support summary views.

## Investigating a Feeding side effect

1. Open `/admin/incidents` and enter the account email, Animal UUID, event UUID, or correlation UUID. Exact IDs resolve to a support bundle; grouped search results link to detailed screens.
2. Follow Account → Household → Animal. The Animal screen shows keeper-visible **effective History** using the same presentation function as the keeper UI. Technical provenance is a separate section and includes internal Inventory events.
3. Open the Feeding event. Follow its correlation and causation links, actor account, and typed subjects. Open the related `inventory.stock_consumed` event, then its source Feeding link. The Inventory Item screen shows both directions of the Feeding/consumption relationship, quantity, actor, Animal, timestamps, and reversal link when present.
4. Treat deterministic warnings as evidence of broken references. For example, a consumption link whose source event is absent is explicitly marked. Verify the source data in the Event inspector before planning any remediation.

The console does not alter Sara's historical Feeding records or any other production event.

## Recorded versus unavailable health

The System page reads job status, completed/failed backup runs, migration revision, event high-water, finalized attachment metadata, local file presence, reference-image cache files, and projection registrations. A completed backup run is shown as such; independent restore verification is labelled **Not recorded** because the current store has no durable result for it. The image build embeds its source Git SHA through `SNAKETRACKER_BUILD_GIT_SHA`; System Health reports that image value, not the working-tree HEAD. Database integrity checks remain **Not recorded** in the UI until an authoritative runtime result exists. An unlisted health signal is not assumed healthy.

List and event searches paginate at 30 rows. Household and subject drill-down sections cap recent results at 100 and label them as bounded. This is an investigation view, not a bulk export.

## Deferred OPS-B actions

Support notes require an append-only, separately audited platform store and remain deferred. User disable/reactivation, password reset, session revocation, Feeding correction, Inventory adjustment, job retry, projection rebuild, image refresh, deletion, and impersonation are also outside this read-only release. None of these actions has an Admin route in OPS-A.

## Data safety

OPS-A adds no database schema migration and needs no reseed or restore. For production set `SNAKETRACKER_ENVIRONMENT=production` explicitly in Compose `.env`, use an HTTPS external origin and secure session cookies, configure valid runtime and backup secrets, and set password-reset delivery to `disabled` while no email adapter exists. Validate the production configuration on isolated storage before recreating services. Build the web and worker from one image with the exact commit SHA embedded, and verify both report production. Use isolated test data for qualification and keep production screenshots private. Never put production incident evidence into Git or a screenshot artifact.
