# M4 Internal Baseline Evidence

Status: **M4 implementation qualified; owner acceptance pending**

- Qualification date: August 10, 2026
- Source branch: `phase4/animal-care`
- Qualified source before final evidence refresh: `3a82acf01b06043e26f0f351c98a3ea3ab70f489`

This package proves the internal, local-only Phase 4 keeper baseline on the approved laptop/Docker
development environment. It does not approve remote/public access, production launch, or Raspberry
Pi deployment. M5 through M8 remain outside this work.

The August 10 keeper-UX requalification preserves the same event, attachment, backup, migration,
and authorization implementation while replacing the oversized profile form surface with a concise
overview, focused care-entry pages, payload-derived effective histories, and a collapsed technical
audit.

The final enclosure-history correction resolves each immutable assignment through the
household-scoped enclosure projection, presents first assignments and reassignments with their
actual enclosure names, retains target identifiers in the technical audit, and withholds the
assignment Void control until projection-aware effective-state rebuilding is designed.

## Evidence inventory

- [Core keeper workflows](core-workflows/README.md)
- [Automated quality and migration results](tests/README.md)
- [Domain-boundary evidence](tests/domain-boundaries/README.md)
- [Attachment security](security/attachments/README.md)
- [Backup and restore rehearsal](operations/backups/README.md)
- [Docker and ARM64 compatibility](containers/README.md)
- [Real-browser evidence](browser/README.md)
- [Accessibility evidence](accessibility/README.md)
- [Final review disposition](reviews/README.md)
- [Release disposition](approvals/release/README.md)

## Milestone disposition

All applicable M4 release blockers have implementation evidence. The remote/public-deployment item
remains unchecked and deferred. The owner has not yet accepted M4, so the milestone is not recorded
as accepted and Phase 5 is not authorized.

The retained databases, generated archives, test credentials, and local browser tooling state stay
under ignored `runtime/`, `output/`, `.playwright-cli/`, and `secrets/` paths. They are deliberately
not part of the repository evidence set.
