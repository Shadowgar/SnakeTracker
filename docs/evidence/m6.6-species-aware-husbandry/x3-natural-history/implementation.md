# X3 implementation record

Owner authorization: October 18, 2026, build X3 from main
`94ea887f4302e58eae18985c34f3f910da2df2c9`; PR review only, no production operations.
Controlling design: October 1 implementation plan, ADR-0047 (status unchanged), R-100/R-103.

Implementation tasks:
1. Add migration 0025, permanent-UUID source associations, immutable retained versions,
   explicit content-bound publication/withdrawal with optimistic concurrency and rights gate.
2. Add trusted contextual/origin-aware biological presentation with exact-version legacy
   guide bindings; preserve full immutable guides and never infer husbandry from wild facts.
3. Extend existing animal/reference and directory pages with local Natural History;
   compact image-led cards, honest missing states, attribution and retained-version detail.
4. Qualify Boa imperator / iNaturalist 539399 in an isolated fixture, version/publication/
   rollback races, migration preservation, offline read purity, privacy and guide compatibility.
5. Capture real browser views, run focused checks then hosted gates, review and open focused PR.

Ruling: use the existing approved architecture and execute inline; no new design approval
round or architecture amendment. No source acquisition during requests, new queue, provider
transport, or bulk enrichment. Explicit operator bundle import is offline and dry-run by default.
Production publication requires independently qualified rights evidence and exact-content selection.

Progress: implementation and screenshots complete. Lifecycle, semantic, operator, offline-read
and isolated upgrade tests pass. A wider 244-test local reference regression run had 243 passes
and one stale expected-schema assertion (0024 versus new head 0025); that assertion was updated
to preserve the same downgrade-blocking invariant and its focused rerun passed. No gate threshold
or functional assertion was relaxed. Final full qualification uses fresh ordinary hosted checks.

Review: fresh reviewer identified missing selection detection and guide life-stage/absent-qualifier
issues; all corrected with regression cases. Reviewer rechecked and reported no remaining substantive
findings. Source and guide identity/hash/origin guards remain explicit. No protected document or
existing ADR status was changed. Implementation uses the approved controlling plan directly.
