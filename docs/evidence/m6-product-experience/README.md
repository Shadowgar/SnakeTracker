# M6 Product Experience Evidence

Status: **M6 implementation-qualified; owner acceptance pending**

The M6 product experience is qualified on the laptop/Docker development environment. It adds
household-authorized FTS5 search, HTML/CSV reports, capability-aware effective-history analytics,
deterministic estimate windows, an explainable Today page, versioned reference infrastructure, and
a strict-CSP read-only PWA shell. No production husbandry guidance is enabled.

- [Tests and compatibility](tests/README.md)
- [Security](security/README.md)
- [Projection and migration operations](operations/README.md)
- [Laptop performance](performance/laptop-container/README.md)
- [Containers and ARM64](containers/README.md)
- [Real-browser evidence](browser/README.md)
- [Owner-review demo and login recovery](owner-review/README.md)
- [UX Overhaul Pass 4 owner-review evidence](owner-review/ux-pass4/README.md)
- [Accessibility](accessibility/critical-journeys/README.md)
- [Reference-content gate](references/provenance/README.md)
- [Review status](reviews/README.md)
- [Approval status](approvals/README.md)

Native Raspberry Pi execution, SSD/ext4 placement, thermal behavior, and deployment performance
remain Phase 7/pre-deployment qualifications. M6 does not approve remote or production deployment.

The accepted [ADR-0040](../../adr/0040-trusted-local-demo-household-provisioning.md) correction is
implemented and qualified. The [single-instance demo/isolation evidence](owner-review/consolidated-demo/README.md)
and [mobile-first owner-review correction](browser/mobile-first/README.md) pass. M6 owner acceptance
remains pending.

The later [ADR-0041 four-group extension](four-group-expansion/README.md) is
implementation-qualified on the promoted Raspberry Pi 5 and tracked separately so
the accepted M5.5 and earlier M6 evidence continues to describe its original Snake/Spider scope.
The four staged UX implementation passes are deployed for owner review; M6 owner acceptance is
still pending. Newly triaged owner corrections are prospective requirements `R-065`–`R-069` and
later-discovered phone-photo requirement `R-082` in [M6.1](../../roadmap/milestones.md#phase-61--m61--final-usability-and-correctness-corrections).
M6.1 implementation and owner review must precede complete final M6 qualification, green
authoritative CI, PR #8 review readiness, and explicit owner acceptance. This status note does not
rewrite the historical evidence above or begin those corrections.
