# M9 public Animal profiles, photo albums and collections

Development base: `a0975ef28937ecb11d0fe8da59d40eaab1886535` (PRs #34–#36 merged).
Production remains source `cf772cf8348f3eeb2ec069754b585bffd6c926cf`, schema 27.
This candidate is not a deployment, public enablement or milestone acceptance.

## Scope and authority

The [frozen M9 roadmap](../../roadmap/milestones.md#phase-9--m9--public-profiles-albums-and-media-sharing)
and R-077–R-081 govern this work: public profiles and collections connected to
Animal photo/video albums. The November 8 owner directive authorizes implementation
of the public-photo vertical slice. The earlier private-album handoff is historical
and does not narrow the scope. [Proposed ADR-0049](ADR-0049-proposed-public-sharing.md)
records the identity, media, privacy, storage and release choices for review.

M0–M6.5 have delivered functionality and historical acceptance, subject to recorded
standalone gaps. M6.6 X1–X5/C/D are implemented and deployed; the
[acceptance audit](../m6.6-final-acceptance-20261108/requirements-audit.md) preserves
the pending A/extension/consolidated decisions, manual evidence and taxonomy/content
gates. Those open items neither become complete here nor block this independent
development assignment. M7/M8 remain incomplete public-release gates.

## Requirements and compatibility supplement

This supplements the frozen traceability matrix without changing its approved bytes.

| Requirement | Candidate behavior | Acceptance boundary |
| --- | --- | --- |
| R-077 / AT-PUB-01 | Multiple photos with upload, caption/order and removal; immutable attachments retained; primary photo remains separate | Photo slice only; video remains required within M9 |
| R-078 / AT-PUB-02 | Explicit public snapshots; human-friendly independent public slugs; public Animal and collection pages | No raw private identifiers or household data; production delivery unavailable |
| R-079 / AT-PUB-03 | Household, Animal and media opt-in; private defaults; current-state checks revoke delivery after unpublish/archive/removal | No-store delivery; downloaded visitor copies cannot be erased remotely |
| R-080 / AT-PUB-04, AR-PUB-01 | Existing raster processing/metadata stripping; body/image bounds; safe delivery/rate limits; retained-byte quotas and disk reserve | ADR approval, native public load/proxy/storage evidence and video qualification remain open |
| R-081 / AT-PUB-05 | Explicit public DTOs, tenant/role/CSRF enforcement, anonymous denial and uniform unavailable responses | Independent security review and owner acceptance required before enablement |
| R-082 reuse | Existing orientation-correct, metadata-stripped finalized image processing | Does not authorize arbitrary files, provider acquisition or raw original delivery |

Schema 28 adds publication/album current-state projections and new versioned sharing
events. Existing schema-27 records remain private and retain original identity.
The candidate qualifies additive preservation, event replay, encrypted recovery
of removed/retained images and refusal by the actual previous binary. Older source
cannot be treated as a binary rollback after schema 28 is installed. The existing
backup format and immutable finalized-attachment inventory remain authoritative.

## Public-release gates kept open

- Owner approval of ADR-0049 and the applicable M9 independent security/acceptance evidence.
- Off-device encrypted recovery and independently recoverable keys. The owner must
  identify an existing separate destination and key custodian; do not invent one or
  require a purchase. Same-device restoration is useful evidence, not off-device recovery.
- Native Pi performance/thermal/storage/durability budgets, public proxy/upload/rate
  behavior and the formal SD-only exception disposition. No SSD investigation or
  hardware purchase is part of this development task.
- Complete supported fresh-install/upgrade/rollback/event/projection/plugin/backup
  matrix, artifact SBOM/signature evidence and operator incident/recovery exercises.
- Video upload/processing/poster/privacy/bandwidth/retention qualification and final
  M9 review. M9 is not complete when the photo slice is delivered.

The application rejects production public enablement in this first slice even if
the default-off flag is set. A later reviewed release change must establish the
required evidence before lifting that restriction. No cloud provider, destination,
financial commitment, production migration or public-sharing change is authorized.

## Next M9 implementation slice: video

Qualify a bounded video policy and implement it in the same album/publication model.
Decide supported containers/codecs, bytes/duration/resolution, metadata removal,
processing isolation and bounded queue/concurrency, poster images and authorized
range delivery; include retained-storage/backup accounting and revocation tests.
Measure whether the existing Pi can safely provide that scope before committing
to local transcoding. Any separate media/object store needs a focused architecture
decision and owner approval before provider adoption. This is remaining M9 work,
not a deferred capability outside the milestone.

## Implemented photo experience

The Animal profile now links to a separate album and public-profile choices. Owners
upload processed photos, edit captions and order, select shared photos and a public
cover, and remove album entries without changing the primary photo or deleting
retained versions. Archived Animals retain authenticated read-only album access;
restoring one does not silently republish it.

Collection controls at `/sharing` prepare deliberately entered visitor text and
independent public links. Authenticated previews work with public delivery disabled.
The isolated development/test visitor experience serves collection, Animal and
selected-media routes; public HTML contains no private navigation or record IDs.

## Focused qualification

- **25 new-feature tests passed together** after the final archive-access correction:
  `tests/integration/test_public_sharing.py`, `test_public_sharing_recovery.py`,
  `tests/browser/test_public_sharing.py`, and the new configuration, guard and form-bound
  unit tests. Coverage includes all three visibility levels, tenant/role/CSRF denial,
  malicious files, image metadata removal, quotas and concurrent upload admission,
  replay, error/HEAD cache headers, archive/restore, mutation conflicts and recovery.
- **126 directly affected backend, attachment, migration, compatibility, operator and
  backup checks passed** during implementation. These counts describe separate test
  invocations and are not asserted to be a unique combined application-suite count.
  Historical schema-26/27 probes remain pinned to their original revisions; current
  head expectations and the existing Natural History operator allowlist now accept 28.
- Encrypted backup, verification, isolated restoration and sharing-projection rebuild
  preserve all seven checked event/subject/attachment/Animal/sharing tables and both
  visible and removed immutable photo versions. Restored public delivery remains revoked.
- The **actual deployed ARM64 binary** at `cf772cf` was run only against a disposable
  schema-28 fixture. Web startup reports `recovery_required / relational_schema_unknown`;
  worker exits 2. The database SHA-256 remains unchanged. The
  [old-binary receipt](old-binary-refusal.json) records the exact image and corrected
  fixture harness. No image rebuild, scan, production execution or binary rollback occurred.
- The automated Chromium journey performs real multipart uploads, changes captions/order,
  sets a separate public cover, enables all three publication levels, visits public
  profiles/collection without a session, revokes media and profile access, and confirms
  the primary image is unchanged. It captures 23 owner/visitor states at **1440/390/320 px**,
  including empty collection/album, missing photo and long names. All pass horizontal
  overflow, bounded image and axe WCAG A/AA checks with zero JavaScript errors or external
  requests. A scoped mobile owner-spacing refinement is checked separately.
- A fresh independent reviewer examined the complete production diff and final security
  delta: no confirmed vulnerability. This bounded review does not close proxy, native
  capacity, independent key recovery or public-release acceptance. See
  [security review](security-review.md) for the exact source binding and limitations.
- Ruff, formatting, full mypy, architecture boundaries, architecture freeze, documentation
  links and whitespace checks pass. Required hosted PR checks qualify the new candidate;
  they do not replace or repeat the accepted deployed-image receipts.

The browser fixture is temporary, loopback-only and fictional. Its two uploaded images
use the existing group illustration, not a claimed photograph of a real keeper's Animal.
The reproducible harness is `scripts/qualification/m9_public_sharing_fixture.py` plus
`m9_public_sharing_browser.js`; no owner device, Tailscale or production fixture is needed.
All private execution logs remain in `output/m9-public-sharing-20261108/`.

Early parallel local runs encountered one browser authentication lock and pytest
timeouts during filesystem writes. Serialized final feature tests and browser checks
passed. No unrelated session-authentication change or storage investigation was made;
these local results are not native performance/durability acceptance.

### Hosted qualification correction — November 12 continuation

The initial candidate's hosted quality run passed 1,743 tests and failed one
obsolete five-tab expectation: the new Album tab makes six. The corrected assertion
checks all six and the Album destination. Its ARM64 image built successfully, then
the runtime probe rejected the new migration because its declared chain ended at
27. The probe now requires 28 and runs a populated 27 → 28 → 27 → 28 preservation
check, sharing-event replay and refusal of downgrade after retained sharing history,
using only release-installed dependencies. These six focused correction tests pass.
Application and migration bytes are unchanged from the independently reviewed
candidate; existing browser/security evidence retains its original scope. Final
hosted check identities are attached to the PR head, without claiming failed runs
passed or regenerating accepted production artifacts.

## Review screenshots

- [Public Animal, desktop](screenshots/public-animal-1440.png)
- [Public Animal, 320 px](screenshots/public-animal-320.png)
- [Collection, 390 px](screenshots/public-collection-390.png)
- [Owner album, 390 px](screenshots/owner-album-final-390.png)

[Full browser results](browser-results.json) retain 23 page checks plus the complete
owner-to-visitor journey. [Final mobile owner results](owner-mobile-results.json)
retain the six scoped gutter checks. The images contain fictional fixture data only.
