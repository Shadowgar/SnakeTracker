# Phase 4 Animal Care Implementation Plan

**Status:** Revised August 7, 2026; implementation authorized on `phase4/animal-care`.

## Goal and authority

Deliver the internal M4 keeper workflow defined by [the milestone roadmap](../roadmap/milestones.md),
R-003, R-018, R-019, R-035, and R-036 in the requirements traceability matrix, and ADR-0004,
ADR-0006, ADR-0017, ADR-0018, ADR-0034, and ADR-0035. This remains a secure local-only internal
baseline; remote/public access and Raspberry Pi qualification remain deferred through Phase 7.

The primary browser journey is: log in; view animals; add a snake; open its profile; record a
feeding, weight, length, shed, and bath/soak; create and assign an enclosure; record cleaning and a
water change; review effective history; correct an erroneous keeper entry; add/select a profile
photo; and produce and verify a basic backup.

## Visible surfaces and routes

| Surface | Routes and submitted command forms |
|---|---|
| Animal list | `GET /home`, `GET /animals`, with direct add-animal and open-profile actions |
| Animal creation and profile | `GET /animals/new`, `POST /animals`, `GET /animals/{animal_id}`, `GET/POST /animals/{animal_id}/edit`, `POST /animals/{animal_id}/status` |
| Care recording | `GET/POST /animals/{animal_id}/feedings`, `/measurements/weight`, `/measurements/length`, `/sheds`, and `/baths` |
| Histories and correction | `GET /animals/{animal_id}/feedings`, `/measurements`, `/timeline`; `GET/POST /animals/{animal_id}/events/{event_id}/correct`; protected void and reinstate commands |
| Enclosures | `GET /enclosures`, `GET/POST /enclosures/new`, `GET /enclosures/{enclosure_id}`, `POST /animals/{animal_id}/enclosure`, and maintenance forms for cleaning and water changes |
| Profile photo | stage, finalize, and select commands under `/animals/{animal_id}/photo`; authenticated `GET /attachments/{version_id}` delivery |
| Backup | `GET /settings/backups`, `POST /settings/backups/run`, and `POST /settings/backups/schedule`; restore rehearsal is an operator-only command, not a web endpoint |

All mutations keep the existing authenticated-principal, same-household authorization, origin, and
CSRF controls. The profile is the primary care surface, with one-tap/touch-sized record actions;
desktop presents denser summaries while phone layouts preserve the same workflow.

## Domain contracts and projections

- Register animal profile/lifecycle contracts: `animal.registered`, `animal.profile_corrected`,
  `animal.status_changed`, `animal.enclosure_assigned`, and `animal.photo_selected`.
- Register husbandry contracts: `animal.feeding_recorded`, `animal.feeding_corrected`,
  `animal.weight_recorded`, `animal.weight_corrected`, `animal.length_recorded`,
  `animal.length_corrected`, `animal.shed_recorded`, `animal.shed_corrected`, and
  `animal.bath_recorded`.
- Feeding payloads record occurred time, prey type/size/optional weight, preparation method,
  quantity, accepted/refused/regurgitated outcome, and notes. The effective profile shows last and
  days since last accepted feeding; history retains corrected effective entries.
- Measurement payloads retain entered and normalized weight/length, occurred time, and notes. Shed
  payloads record blue/in-shed observations, completion, complete/incomplete result, occurred time,
  and notes. Bath/soak payloads record occurred time, duration, reason, and notes.
- Register `enclosure.registered`, `enclosure.profile_changed`, `enclosure.cleaning_recorded`,
  `enclosure.water_change_recorded`, and `enclosure.status_changed`. Animal owns assignment;
  occupancy is derived from animal streams.
- Add synchronous `animal_current`, `animal_effective_timeline`, `enclosure_current`, and
  `enclosure_occupancy` definitions. Do not add asynchronous analytics, charts, search, or a
  dashboard.

### Narrow `animal.shed_corrected` catalog amendment

`animal.shed_corrected` is required because M4 requires keeper corrections while a generic void is
not an edit: it cannot replace an erroneous occurred time, blue/in-shed state, completion result,
or notes with one explicit effective fact. Its v1 payload carries `target_event_id` plus the same
replacement shed facts as `animal.shed_recorded`; the target must be a permitted shed event in the
same animal stream and household. The target is never rewritten.

The registration is correctable, voidable, and reinstatable and permits only the explicit shed
correction contract for replacement. Applying it supersedes the target's effective facts; reversing
or voiding it restores the prior effective predecessor; reinstating it reapplies its replacement.
The timeline retains each link and renders the current effective entry without hiding the audit
chain. Replay reads historical `animal.shed_recorded` records unchanged, applies later correction
events in stream order, and fails safely on an unknown newer contract. No event-envelope, aggregate,
storage, migration, or stream-boundary rule changes.

This is a catalog refinement within the accepted Animal husbandry family, not a new architectural
decision. The owner-approved amendment record is retained under M0 evidence. Any need to alter
aggregate ownership, envelope semantics, correction platform behavior, or compatibility policy
stops implementation for ADR-0028 review.

## Storage, attachment, and backup work

Add one forward Alembic revision for staged/finalized attachment records, backup operations and
schedule configuration, and M4 operational indexes. Generic event tables remain the sole source of
business history; projection generations create their registered read models.

The M4 attachment scope is profile photos only. Uploads stage under bounded size/type/dimension and
active-content controls, finalize to immutable random-key versions with checksum and detected type,
then select the finalized version through `animal.photo_selected`. Staging is never directly served
or backed up; delivery requires current household authorization and safe response headers.

Implement the real ADR-0018 basic path: the backup worker is the sole initiator, obtains one backup
lease, accepts on-demand requests and scheduled local execution, creates a consistent SQLite online
copy first, derives attachment references from that completed copy, copies exactly those immutable
versions, writes a versioned encrypted manifest, checksums and verifies every artifact, and excludes
or invalidates sessions and temporary credentials as required. Rehearse an isolated local restore.
M4 does not claim off-device retention, independent production-key recovery, qualified recovery
objectives, upgrade/rollback recovery, or native Raspberry Pi backup/restore evidence; those remain
Phase 7 work.

## Test-driven delivery and evidence

1. Add failing domain/replay/authorization tests for animal profile and lifecycle contracts, then
   implement the animal-owned application port and current projection.
2. Add failing care-contract and effective-state tests for feeding, weight, length, shed, bath, and
   correction/void/reinstate chains; then implement the handlers and profile/history reads.
3. Add failing enclosure assignment, occupancy, cleaning, water-change, and timeline integration
   tests; then implement the enclosure port and synchronous projections.
4. Add failing browser tests for the primary keeper journey at desktop and phone viewports, including
   keyboard, focus, error-summary, and screen-reader assertions; then implement the server-rendered
   forms and responsive templates.
5. Add failing adversarial profile-photo tests for active content, resource exhaustion, cross-
   household access, staging isolation, immutable delivery, and orphan cleanup; then implement the
   attachment flow.
6. Add failing backup tests for worker-only initiation, lease exclusion, scheduled/on-demand runs,
   copy/manifest ordering, attachment selection, encryption, checksums, verification, session
   handling, and isolated restore rehearsal; then implement the backup pipeline.

Evidence remains under the existing `docs/evidence/m4-internal-baseline/` root: `core-workflows/`,
`tests/`, `security/attachments/`, `operations/backups/`, `browser/`, `accessibility/`, and
`approvals/`. Existing traceability paths remain authoritative, especially
`m4-internal-baseline/security/attachments` for R-018 and
`m4-internal-baseline/approvals/release` for R-036. Retain exact commands, revisions, environment,
raw results, and reviewer/owner disposition for each M4 release blocker.

## Proposed commit sequence and exclusions

1. `docs: refine Phase 4 animal care plan and shed contract amendment`
2. `test: define animal profile and husbandry contracts`
3. `feat: add animal care event slice and projections`
4. `feat: add enclosure maintenance and effective timeline`
5. `feat: add safe profile photo attachments`
6. `feat: add verified local backup workflow`
7. `feat: add mobile keeper workflow screens`
8. `test: qualify Phase 4 core keeper workflows`
9. `docs: record M4 evidence`

M4 excludes inventory, expenses, reminder or notification delivery, health/veterinary workflows,
global search, final reporting, analytics/dashboard work, final chart polish, offline PWA writes,
remote/public access, and Raspberry Pi deployment. Bath reminders are excluded; bath/soak remains a
manual keeper record only.