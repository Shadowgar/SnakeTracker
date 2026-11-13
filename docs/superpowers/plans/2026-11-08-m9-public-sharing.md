# M9 Public Photo Sharing Implementation Plan

> Execution: owner-authorized autonomous implementation; backend, presentation and
> release-foundation tasks use separate file ownership and focused test-first checks.

**Goal:** Deliver Animal albums connected to optional public Animal profiles and a
public collection gallery, with production delivery locked pending release gates.

**Architecture:** Proposed ADR-0049 extends existing immutable processed attachments,
events and rebuildable projections. Three independent publication levels and explicit
public snapshots constrain exposure. M7/M8 offline evidence tooling is a separate PR.

**Tech stack:** Existing Python 3.13, FastAPI/Jinja, SQLite/Alembic, Pillow, pytest and
Playwright/axe. No new service, provider, production fixture or image rebuild for setup.

**Spec:** [ADR-0049](../../evidence/m9-public-media/ADR-0049-proposed-public-sharing.md),
frozen R-077–R-082 and the November 8 owner implementation directive.

## Global constraints

- Base `a0975ef28937ecb11d0fe8da59d40eaab1886535`; production remains `cf772cf`/schema 27.
- No merge, production migration/deployment/public enablement or reference import.
- Preserve real user data and existing attachment/event identity; isolated test data only.
- Reuse accepted baseline qualification; focused new-code tests and required candidate gates.
- Public delivery defaults off and production enablement is rejected in this slice.
- Video is the next M9 implementation slice, not removed from the milestone.

## Review focus

- Archive/remove/unpublish after a media URL was previously delivered must deny new requests.
- A cross-household ID, viewer role or invalid CSRF must never mutate publication/media.
- Concurrent uploads and retained removed versions must not bypass disk/quota admission.
- Public HTML, redirects, media headers and error pages must not disclose private identifiers.
- Restored/replayed state and actual older binaries must preserve visibility and fail safely.

## Tasks

- [x] Backend: test defaults, ownership, event idempotency/replay, immutable album lifecycle,
  retained quotas and revocation; implement `application/sharing.py`,
  `domains/sharing/contracts.py`, sharing projection/repository and schema 28; run focused tests.
- [x] Presentation: test authenticated owner controls and anonymous access; implement a separate
  sharing router, templates and scoped CSS, settings/composition and navigation. Explicit DTOs
  keep private profile data out of public templates. Test request bounds, CSRF, rate limits,
  production lock, private previews and all public visibility levels.
- [x] Integration: verify migration preservation, actual older-binary refusal and isolated
  backup/replay. Exercise the coherent owner-upload/publish/visitor/unpublish journey at
  1440/390/320 px with axe and retain screenshots/results. Fix demonstrated defects.
- [x] Governance: proposed ADR and evidence/traceability/compatibility supplement; record
  pending owner architecture/content/release decisions without modifying accepted history.
- [x] Independent review: review the exact application diff for publication, upload, retention,
  tenant authorization and revocation flaws; reproduce and resolve findings before delivery.
- [ ] Delivery: focused M9 PR plus separate release-foundation PR, accurate tests/data/security
  evidence and limitations; leave both unmerged and production disabled.

The M7/M8 task implements offline standard SBOM and hash/signature evidence handling
from retained artifacts. It cannot invent an off-device destination, independent key
recovery, native storage exception acceptance or completed incident exercises.
