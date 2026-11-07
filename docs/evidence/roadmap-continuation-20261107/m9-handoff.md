# M9 handoff — private Animal albums first

Prepared November 7, 2026. This is a bounded implementation handoff, not an
implementation or public-enablement approval. It applies the existing
[M9 requirements](../../roadmap/milestones.md#phase-9--m9--public-profiles-albums-and-media-sharing),
[immutable attachment design](../../adr/0017-immutable-attachments.md) and
[architecture approval process](../../adr/0028-architecture-governance-and-decision-freeze.md).

## First useful development task

**Add a private Photos album to each Animal, with multiple processed photographs,
upload/view/remove controls and clear empty/loading/error states.** Keep the primary
profile photograph and its existing reference separate. All existing and new album
content stays household-private; this slice introduces no public routes or videos.
Use the established Care Keeper cards, actions, responsive spacing and image style.

Reuse `application/attachments.py` and its storage/processing boundary: bounded
JPEG/PNG/WebP inputs, orientation correction, fresh derivatives without EXIF/GPS,
immutable finalized versions, household authorization, idempotency and lifecycle
locking. Current limits are 20 MiB input, 8,192 px edges / 25 megapixels and a
1,600 px processed long edge; HEIC is currently unsupported. Do not broaden these
limits or expose original uploads to make the album work.

The implementation should add explicit Animal-to-album-item membership and ordering,
not overload the primary-photo reference. Finalized media must be owned by the same
household and Animal before association. Removing an item hides it from the active
album while preserving the immutable history/backup contract; orphan cleanup must
not delete a version still referenced by retained events or recovery data.

Acceptance for this first slice: two independent photos can be added, viewed and
removed without changing the primary photo; retry does not duplicate membership;
cross-household and anonymous access fail; misleading types/oversized files/failed
finalization leave no published item; orientation and metadata stripping persist;
quota reservation is safe under concurrent uploads; retained media restores with
its associations; 320 px, 390 px and desktop journeys work with keyboard and named
controls. Use isolated data for writes and meaningful focused tests.

## One concrete storage and capacity decision before coding

Approve the initial private-photo storage adapter and a retained-byte budget per
household, per-Animal count limit, per-file derivative limit, staging reserve and
minimum free-space stop threshold. Decide how hidden/removed versions count until
retention permits deletion, and include encrypted backup/off-device capacity.
The proposal is to reuse the existing local immutable attachment adapter for a
**bounded photo-only pilot**, conditional on measured capacity and an approved
budget; no quota values or sufficient headroom are asserted by this handoff.

The owner's SD-only exception remains acknowledged. Local albums must not silently
consume the recovery reserve or assume that deleted UI items free retained bytes.
If the local budget cannot support the approved pilot, select a compatible object
store and document credentials, private serving, recovery and retention before
implementation. Cloudflare R2 is an option already mentioned by the roadmap, not a
selected provider. No storage purchase or new platform is prescribed here.

## Minimum secure sequence

1. Resolve the relevant release/recovery prerequisites and the bounded storage
   decision above. Record album identity, retention and capacity choices through
   the existing architecture process; do not reopen unrelated taxonomy work.
2. Implement and qualify the private photo album slice. Preserve primary-photo
   behavior, private media delivery and old event/attachment compatibility.
3. Prepare an explicit public profile projection and private preview. Approve its
   small field allowlist, opaque public identity/URLs, cache invalidation,
   revocation and abuse limits. Public output must not serialize the Animal or
   household model wholesale or reveal raw internal identifiers.
4. Add household opt-in **and** per-Animal publication **and** deliberate per-media
   visibility. Unpublish/archive/delete must fail private, including cached media.
   Care history, expenses, schedules, inventory, notes, backups and operational
   records are excluded unless a later explicit product/privacy decision changes
   that boundary. Existing records never become public through migration defaults.
5. Qualify anonymous/cross-household negative cases, public/private journeys,
   accessibility, capacity and revocation. Obtain independent security review and
   owner acceptance before enabling public pages; then add the opt-in collection
   gallery listing only explicitly public Animals and media.
6. Plan videos separately with upload/processing/duration/codec/storage/delivery
   budgets. Do not send unbounded video processing or public delivery to the Pi.

Payment processing, subscriptions and universal Animal capability modules remain
later expansion. The next development authorization should name **private Animal
photo albums**, the approved storage budget and the resolved prerequisites; it
should not implicitly authorize public sharing or video support.
