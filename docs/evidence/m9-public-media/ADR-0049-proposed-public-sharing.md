# ADR-0049: Explicit Public Animal, Album and Collection Publication

Status: Proposed

Review location: this candidate records the complete proposed decision here until
content-bound owner approval allows registration in the frozen ADR index. No
accepted architecture or index bytes are changed by this implementation branch.

## Context

The frozen M9 roadmap requires photo and video albums, optional public Animal
profiles and collection galleries, and three independent publication permissions.
The owner authorized the first public-photo implementation on November 8, 2026.
That development direction does not itself accept this architecture or complete
M6.6, M7, M8 or M9. The earlier private-album handoff is not the governing M9 scope.

The existing single primary photo, immutable attachment versions, validated raster
processing, event store, projections, household authorization and encrypted backup
pipeline remain the foundation. Production has irreplaceable keeper records and
limited local storage. No production migration or public enablement is authorized.

## Proposed decision

### Publication model and routing

Keep the album distinct from the primary profile-photo reference. Album add,
caption/order/visibility changes, removal, household publication and Animal
publication are immutable events with synchronous rebuildable projections.
Removing an album entry revokes access; it does not erase attachment/event history.
Existing primary photos are never implicitly added to a public album.

Use separate public publication snapshots containing only explicitly entered
display title, species label and public description. Private Animal edits do not
silently change that published snapshot. Collection title/description are also
deliberately entered; never substitute a household name, account or keeper notes.
Public DTOs contain no household, user, Animal, event, attachment or storage UUIDs.

Public routes are `/p/{public_slug}`, `/c/{public_slug}` and
`/m/{public_media_token}`. Slugs combine a bounded human-friendly label and an
independent random suffix; media receives a distinct opaque random token. Slugs
are identifiers, not authorization. Every page/media request must check current
household enablement, Animal publication and active status, and applicable media
visibility/removal. A public cover is an explicit selection from public album media.
Private/disabled/removed targets return the same unavailable response as unknown
targets. Empty collections reveal no hidden Animals or private counts.

### Owner authorization and release gate

All levels start private. Household enablement requires household-management
authority; Animal/media mutations require the established management capability
and exact current-household ownership. Normal authentication, CSRF, idempotency,
and command validation apply; identifiers supplied by the client are never authority.

`SNAKETRACKER_PUBLIC_SHARING_ENABLED` defaults to false. The photo candidate allows
explicit enablement only in isolated development/test environments and rejects
enablement in production. Authenticated albums, publication preparation and private
previews remain usable with the gate off. Enabling anonymous production delivery
requires a subsequent reviewed change after the applicable M7/M8 evidence, this
architecture decision, independent security review and owner release approval exist.
An environment variable is not proof that those gates passed.

### Media security, delivery and capacity

Reuse the validated raster decoder, orientation correction, metadata stripping,
bounded dimensions and immutable finalized versions from ADR-0017/R-082. Uploads
must pass bounded request/body and decoded-image checks. Do not serve originals,
filenames, filesystem paths, raw EXIF/GPS, provider URLs or arbitrary active content.
Photos remain JPEG/PNG/WebP inputs under the existing 20 MiB/25-megapixel bounds.

Serve public derivatives through the authorization-aware application route with
safe media headers and `Cache-Control: no-store`. No public static directory,
CDN cache, immutable URL cache, service-worker media cache or conditional 304 bypass
is introduced. Recheck access before delivery, including HEAD and conditional
requests. Previously downloaded copies cannot be remotely erased; the guarantee
is denial of subsequent application delivery after revocation, not deletion from
a visitor's device. Apply bounded public request rate limits without trusting
arbitrary forwarded client-IP headers.

Start with 100 active album photos per Animal and 256 MiB retained attachment
bytes per household, including removed immutable versions and staging. Serialize
quota admission across processes. Preserve at least 6.25 GiB filesystem reserve
and account for new upload/derivative and subsequent backup demand before admission.
Removal does not return retained-history capacity. Expose understandable quota
errors rather than delete old recovery material or increase limits silently.
These are conservative development defaults, not native public capacity acceptance.

### Video stays within M9

The next M9 implementation slice must qualify supported video containers/codecs,
upload bytes and duration, metadata removal, bounded processing/transcoding and
poster generation, bandwidth, visibility, retained storage and recovery. The photo
slice rejects video uploads; it does not declare video complete or defer it outside
M9. Prefer existing local boundaries only if measurements justify them. Do not run
unbounded Pi transcodes or choose an object/media-store provider without the required
architecture approval and capacity/financial decision.

## Alternatives and tradeoffs

- Overload the primary photo or build only a private gallery: fails the explicit
  separate-album and owner/visitor M9 requirements.
- Reuse private records directly in public templates: too easy to expose later
  private fields; explicit publication snapshots are more work but constrain output.
- Public static objects or long-lived signed URLs: cheaper delivery, but immediate
  unpublish cannot revoke an already cached object. No-store application delivery
  is bounded and simple for the first slice, with native load qualification still due.
- Introduce an external object store now: premature provider, credentials and cost
  commitment without measured need. Keep the existing storage abstraction.

## Migration, events, plugins and recovery

Add schema 28 publication/album projections without rewriting existing records.
Existing Animals and attachments gain no public state. Register new versioned event
contracts and replay handlers; preserve their distinct stream identity. Advertise
schema 28 in compatibility metadata; older binaries must refuse mutable startup
before touching newer data. A binary downgrade is not a database rollback.

Album content uses the existing finalized-attachment inventory and checksum/backup
contract. Isolated recovery must preserve retained and removed-photo versions,
publication events and rebuilt visibility. No plugin ABI or trusted-plugin policy
changes are proposed. New event support remains subject to the existing conservative
unknown-contract compatibility rules.

## Qualification and approval consequences

Required evidence includes additive migration preservation; deterministic replay;
actual old-binary refusal; encrypted backup/isolated restore; image metadata and
malicious-file rejection; default-private, anonymous/cross-household and role tests;
all revocation paths including cached/conditional requests; quota races and retained
bytes; desktop/mobile owner/visitor journeys and accessibility; and independent
security review. Record limitations rather than infer completion from a passing test.

[M9 traceability and compatibility supplement](README.md)
maps this candidate to R-077–R-082 and the unchanged frozen roadmap. Accepted ADRs
and protected baseline requirements remain unchanged. This proposal needs explicit
content-bound owner approval under ADR-0028; no acceptance date is asserted.
M7/M8 off-device/key/native-storage/compatibility/SBOM/signing/incident requirements
remain public-release gates, independently of implementation progress.
