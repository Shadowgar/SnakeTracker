# M6.6 final owner acceptance package — November 8, 2026

**M6.6 IMPLEMENTED AND DEPLOYED — FINAL OWNER ACCEPTANCE PENDING**

The combined release and Plant Detail correction are deployed and verified. Final
acceptance remains open: actual-iPhone/accessibility evidence and explicit owner
decisions are missing, and full taxonomy archive qualification is genuinely
incomplete. “Implemented and deployed” describes the delivered application; it
does not waive that mandatory requirement or imply content publication.

## Completed features and retained evidence

Directory/plant identity, sourced Care Guides, capability profiles, local taxonomy,
Natural History functionality, amphibian support, Smart Care and Bioactive plant
care are implemented. The [requirement audit](requirements-audit.md) maps all
**22 frozen checklist rows and R-086–R-103** to evidence and remaining boundaries.
OPS-A has explicit September 27 acceptance; M6.6-B has explicit October 5 acceptance.
Neither record supplies the missing standalone A acceptance or accepts later tranches.

The [release history](release-history.md) preserves the November 4–6 original
deployment, November 7 unsuccessful attempt/healthy rollback, and November 8
successful retry. The latter deployed source
`cf772cf8348f3eeb2ec069754b585bffd6c926cf` in ARM64 image
`sha256:1f9ea52a9ce535f50a2d5e4795d5f62b13c0dc4f297ac58191d6bbf1611cdc39`.
Its dated verification records schema 27, recovery point
`741e4100-8f62-4146-9f2d-d596f9c3bc79`, 1,053 events, 46 attachment versions and
12 retained backups, with a 28.27-second interruption. The closeout measured
7.02 GiB free; no new production inspection was performed for this package.

Reuse the accepted 1,719-test qualification, exact-image security result, recovery
and preservation checks, and deployed Chromium/axe results. Plant Detail passed
1440/390/320 px with proportional bounded photos, accessible Watering/History,
retained attribution and no horizontal overflow or automated accessibility
violations. These checks do not establish physical-device or VoiceOver acceptance.

## Remaining acceptance gates and decisions

| Item | Recommendation and required owner record | Status |
| --- | --- | --- |
| Real iPhone, keyboard and VoiceOver | Complete the [short manual checklist](manual-acceptance.md), recording device/settings, actual results and any failures. Browse/edit/preview/cancel only in production; confirmation and error tests need an isolated fictional fixture. Fixture access is not yet prepared. | Pending |
| Historical A and extension acceptance | Record an explicit present-day A disposition and review X1–X5/C/D/E evidence and the pre-C acceptance sequence. Preserve the existing OPS-A/B approvals; do not backdate missing acceptance or infer it from deployment. | Pending |
| Exact two Frog Guides | Review the [bounded publication decision](content-decisions.md#two-frog-care-guides). Recommend the reviewed version-1 bundle for *Pelodryas caerulea* and *Ceratophrys cranwelli*, subject to source/design review and exact live-taxon eligibility. It adds two guides/five source pages/42 claims; no keeper records or schedules change. Publication requires separate explicit authorization. | Unpublished; decision pending |
| Full taxonomy archive | Actual-archive source/rights, capacity and operational qualification is a frozen requirement. If the deployed bounded catalog is sufficient, explicitly approve a scope amendment through roadmap governance; otherwise separately authorize the missing qualification. A recommendation is not a valid deferral. | Genuinely incomplete; acceptance blocker |
| Natural History production content | Keep the development Boa fixture unpublished. Explicitly dispose of applicable production-publication gates; any production prose needs separate source/revision/rights qualification. Functionality is delivered, but development rights cannot be relabeled as production rights. | Content/acceptance disposition pending |
| Consolidated milestone acceptance | Resolve required manual checks and mandatory gate dispositions, then record explicit owner acceptance or retain named open items. Review and merge of this documentation alone cannot accept M6.6. | Pending |

[Content decisions](content-decisions.md) preserve the exact bundle hash, copyright
limits, species restrictions and proposed taxonomy/Natural History dispositions.
Existing explicit deferrals remain limited to their approved scope. The annotated
Swiss Cheese Plant image may receive a separately qualified replacement if the
owner wants one; that content issue does not invalidate the deployed layout fix.
Formal M7/M8 qualification remains separate; no SSD investigation, new image build
or M9 implementation is needed to prepare this acceptance decision.

## Recommended next roadmap task

Run one bounded **M6.6 owner acceptance session on the real iPhone with VoiceOver**,
after arranging the isolated fixture for confirmation/error cases. Record the
content and mandatory-scope decisions above alongside the results. Keep M6.6 at
the pending status until its required evidence and explicit owner disposition
exist. M9 remains a future handoff, not the next implementation task.

This documentation-only package changes no application source, deployment
configuration, production data, reference publication, frozen roadmap/approval
record or milestone acceptance. The documentation PR is for review; merging and
formal acceptance remain with the owner.
