# M6.6-B live owner-review deployment

Authority: owner's October 1 request to deploy the exact qualified PR #17 head, import Boa reference only, verify integrity, and stop.
Review status: Ready for owner review; acceptance pending.

This is deployment evidence. PR #17 remains open, draft, and unmerged. M6.6-B and ADR-0044/0048
remain unaccepted. No X1, bulk taxonomy, Amphibians, or M6.6-C work occurred.
Earlier correction and backup records remain historical; this record supersedes their deferred-deployment state.

## Exact candidate and controlled replacement

Source/OCI/application revision: `f1d4d33c27bdb79be31b7c9fbf33b5291c036377`.
Image: `snaketracker:m66b-owner-review-f1d4d33`.
Image ID: `sha256:233530ff12ca8173872f4211e224d554c6c7b3988d1b6f519588f1a113a5c8df`.

The source tree was clean on `phase6.6/sourced-care-guides`; exact-head Quality and Container
checks were SUCCESS before deployment. The normal Dockerfile built the image with inspected
production UID/GID `1001:1001`, the full build revision, and frozen dependencies. All 35 installed
distributions matched the lock; inspected migration head remained `0023_sourced_care_guides`.
The reviewed Boa JSON is absent from the image, so import used a read-only bind mount.

Maintenance lasted 15 seconds, `2026-10-01T09:56:58Z` through `09:57:13Z`:

1. Capture schema, business-table digests, actual mounts/settings, containers, and attachment hashes.
2. Stop old worker directly, then stop old web directly.
3. Recreate both services from the same built candidate image:

```sh
SNAKETRACKER_IMAGE_TAG=m66b-owner-review-f1d4d33 docker compose up -d \
  --no-deps --no-build --pull never --force-recreate --wait --wait-timeout 120 web worker
```

No mixed old-worker/new-web window occurred. No migration command ran. The existing migration
container's complete State remained byte-identical, including its historical failed state.
Nginx and Cloudflare container identities, images, and start times remained unchanged.
`.env` stayed byte-identical at mode 0600. Per-setting hashes and actual mount source/destination,
read/write flags, root read-only, dropped capabilities, and security options matched the baseline.
Production environment, external origin, secure cookies, operator allowlist, secret files, runtime
paths, and backup settings were preserved. Existing local ext4 runtime storage on the host SD device
was retained; this deployment does not claim SSD or production hardware qualification.

## Health and worker duties

Web, worker, and nginx are running and healthy. Local nginx `/health/live` and `/health/ready`
returned 200. Both application containers report the exact candidate image/revision.
Worker restart count is zero; its captured lifetime log contains no exceptions. All nine active
projection checkpoints are at event 1027 and the stored catalog matches the actual candidate registry.
Reminder facts continue refreshing only their calculation timestamp. The actual backup-worker
constructor remains available with preserved encryption settings; no new backup was requested.

External readiness returned 200 with a browser User-Agent. The Python User-Agent request received
Cloudflare HTTP 403 / error 1010. Neither Cloudflare policy nor tunnel configuration was changed.
This checks the public health endpoint; authenticated owner browser acceptance is still pending.

## Schema and derived search evolution

Alembic revision remained **0023_sourced_care_guides**. All 140 original raw SQL schema objects
remain unchanged. The worker added eight derived search-generation objects, bringing the raw
inventory to 148; all **114 normalized active schema definitions** match, preserving constraints,
indexes, views, triggers, defaults, and SQL literals. No relational migration occurred.

The qualified search handler changed from 4 to 5. The old generation was retained and a new
validated generation became active. Its 569 documents match the corresponding old documents
apart from physical row IDs. Three `animal.taxon_linked` entries and one
`animal.reference_image_preference_changed` entry are excluded by the candidate's existing
keeper-history allowlist, reducing generic care-search documents from 573 to 569. Their original
events and Animal links remain unchanged. This is expected derived search evolution.

**Rollback limit:** a read-only probe of the actual previous image returns
`projection_definition_newer` against the new catalog. A plain container-only downgrade would
fail readiness. No rollback, compatibility bypass, catalog downgrade, reference deletion, or
production database restore was performed. A future rollback needs an explicitly reviewed compatible
recovery procedure; do not improvise destructive cleanup.

## Qualified recovery point

The existing complete encrypted backup was verified before deployment and reverified afterward:

- Run: `8777f5b4-545e-4384-81e6-e50c99553bb8`.
- Manifest SHA-256: `11878c2e09ed66b833a64543a2d2cc7b7fae44f7b9ea8cecf0a6498994aebd76`.
- Cutoff 1027; schema 0023; 46 manifest attachments; archive unchanged.
- Prior qualified restore: 46 DB versions = 46 manifest entries = 46 restored files, zero mismatches.

See the [complete recovery qualification](../backup-completeness/README.md).
No replacement backup was created, and the earlier incomplete 40-photo archive remains historical.

## Bounded Boa reference import

After service health and pre-import integrity passed, the actual candidate
`snaketracker.operations.import_care_guides` CLI ran in a one-off container with network disabled,
read-only root, dropped capabilities, read-only reviewed JSON, and only the existing database
runtime directory writable. The explicit database path was
`/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`.
An ephemeral SQL hook rejected write targets outside the four Care Guide tables and rejected DDL.
The cached exact `snake / Boa constrictor` taxon and Bitey's existing explicit link were confirmed
before import; no taxonomy acquisition or Animal relinking was performed.

| Content | Verified result |
| --- | --- |
| Imported guide | Boa constrictor, version 1 |
| Source records | 7 |
| Sourced positions | 34 |
| Contextual facts | 28 |
| Single source | 22 |
| Corroborated | 2 |
| Sources differ | 4 |
| Rerun | 0 imported; 1 identical; zero SQL writes |

The stored guide equals the reviewed bundle exactly; current pointer and sole Boa version are 1.
Only `care_guide_versions`, `care_guide_sources`, `care_guide_claims`, and `care_guide_current` received
import writes. All preexisting non-Boa guides remain identical. No household rows or events changed.

## Production and attachment integrity

Before/final event cutoff: **1027 → 1027**. There was no concurrent event activity to reconcile.
All 55 unchanged logical dimensions match. Verified preserved users, memberships, Animals,
taxon links, Enclosures, Plants, Inventory, care history, purchases, expenses, reminder rules,
schedules, event history, idempotency, and attachment metadata. Expected logical changes are only
four additive Boa guide tables and the two active search components described above.
Normal reminder calculation timestamps and transient worker backup-lease metadata are operational
changes; a separate immediately-before/immediately-after import comparison preserved other tables.
No unexpected household/business changes were found.

All **46 finalized attachment versions** match version IDs, storage keys, media types, sizes, and
SHA-256. Every actual finalized file passed its size/hash check. All **77 attachment/reference media
files** remain byte-identical. No media was added, removed, or modified. Mismatches: **0**.

## Zero-network profile reads and mobile checks

An isolated process from the exact deployed candidate used **real production data and media mounted
read-only**, a query-only SQLite engine with a write-denying authorizer, and trapped taxonomy,
image-provider, HTTP, DNS, and outbound socket calls. It invoked actual GET route endpoints and
production composition using existing owner principals supplied only inside that diagnostic process.
No session was issued, and no production process networking was changed.

- **61 profiles**, four households: zero trapped outbound attempts and zero attempted SQL writes.
- 36 linked cached-image cases, including **21 selected cached reference images**.
- **3 linked Animals missing optional enrichment**; they retained keeper photos, and the local
  reference-asset handler returned 404 without enrichment. No live fallback-selected example existed.
- **20 keeper-photo paths**; local reference handlers returned 36 × 200 and 3 × 404 as expected.
- Bitey's rendered Overview contains all 28 facts, the 34 positions, and all seven source URLs inline.

This qualifies renderer/composition behavior; it does not simulate a genuine login or certify full
HTTP authentication/middleware. Earlier isolated browser and boundary qualification remains separate.

Actual read-only production-handler HTML and exact candidate static assets were replayed locally
at **390×844**. Profile/inline facts, expanded sources, unsaved `48.5 in` length entry, and unsaved
manual Spider state all measured width 390 without horizontal overflow. Source disclosures opened;
form controls remained usable; visual review confirmed readable manual text and controls.
There were zero POST and external requests. Local replay used an image placeholder and empty search
response for layout only. Real production HTML/screenshots remain private and are not committed.
No fake Animals, care events, measurements, or sessions were created.

## Owner review

Open [Care Keeper](https://tracker.theroccos.us), then:

1. **Unknown Spider:** Add Animal → Spider → unmatched species/trade name → Use manual species entry.
   Save only a genuine intended Animal, or stop before Create. Expect an intentionally unlinked
   Animal and no image requirement or hidden second validation error.
2. **Explicit selection:** Add/Edit a genuine Animal, select a Directory taxon, save once, and reopen.
   Expect the taxon link already present.
3. **Bitey:** Animals → Bitey → Overview. Review Boa identity, At a glance, temperature/humidity,
   feeding, enclosure, lighting, life history, cautions, disagreement positions, and same-page sources.
   Normal reference information must be available without opening the standalone Care Guide.
4. **Real fractional length:** when a real measurement is available, enter `48.5 in`.
   Expect original display `48.5 in`, canonical **1,231,900 µm**, analytics **1231.9 mm**, retained
   correction value/unit, effective reminder source, and exact original/canonical export.
5. **Mobile:** at approximately 390×844, inspect profile/reference, length entry, and manual species.
   Check overflow, readability, controls, and accessible disclosures.

The [sanitized deployment receipt](qualification-20261001.json) includes exact old/new container and
image IDs, source CI checks, service health, backup proof, schema/data comparisons, and bounded
read/layout results. This evidence-only update does not rebuild or replace the deployed f1d4d33 image.
Owner acceptance and any subsequent implementation work remain pending. Stop after this preparation.
