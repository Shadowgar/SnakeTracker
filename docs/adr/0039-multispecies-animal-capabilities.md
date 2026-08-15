# ADR-0039: Multi-species Animal Capability Profiles

Status: Accepted
Acceptance date: 2026-08-11

## Context

The M4 animal experience delivered a complete snake-care slice, and M5 connected it to shared
inventory, expenses, reminders, jobs, and recovery. Treating those snake-specific care actions as
universal Animal behavior would expose irrelevant fields to other keepers and make each new animal
type require another architecture rewrite. Creating a separate aggregate and duplicated subsystem
per animal type would instead fragment household lists, enclosures, feeding, inventory, reminders,
attachments, and history.

Existing M0-M5 events and projections are authoritative. In particular, stored
`animal.registered` version 1 events cannot be rewritten merely to add a type discriminator.

## Decision

The existing Animal aggregate and `animal:{uuid}` stream remain the authoritative boundary for
every supported animal. Household ownership, common identity and lifecycle, photos, enclosure
assignment, feeding, inventory integration, expenses, reminders, timeline, attachments, backup,
authorization, and historical controls remain shared services or Animal feature slices.

Each Animal has a registered, versioned care-capability profile. M5.5 initially registers trusted
application-owned `snake.v1` and `spider.v1` profiles. A profile declares applicable commands,
event contracts, measurements, care schedule kinds, timeline renderers, and UI actions. Identifiers
are selected from the trusted registry, never from arbitrary user input. Capability profiles are
not plugins, executable user configuration, medical guidance, or universal husbandry intervals.

Existing `animal.registered` version 1 means the legacy `snake.v1` profile during replay. It remains
unchanged. New registrations use `animal.registered` version 2, which adds the registered animal
type/capability-profile identity to the typed payload while retaining the established envelope,
stream, ownership, and common profile semantics. Version 2 is a new event contract identity and is
not an in-place reinterpretation of version 1.

Snake behavior remains intact. Weight, length, snake shedding, bath/soak, and the other existing
snake workflows are enabled by `snake.v1`. Spider support reuses compatible shared workflows and
adds typed spider care contracts for molt and premolt history. Enclosure watering or misting is an
Enclosure care fact, recorded in the existing `enclosure:{uuid}` boundary with an optional typed
animal subject; eligibility and UI exposure follow the occupant's capabilities and owner
configuration. It does not make enclosures species-specific.

The application layer validates a requested action against the current registered profile before
issuing a command. Presentation derives navigation, focused forms, schedule choices, and human
timeline labels from allow-listed view definitions associated with those capabilities. Domain
handlers still enforce the invariant; hiding an action in the UI is not authorization.

## Initial capability allocation

| Capability | `snake.v1` | `spider.v1` | Ownership |
|---|---:|---:|---|
| Common identity, status, notes, photos | Yes | Yes | Animal |
| Feeding outcome, refusal, and prey facts | Yes | Yes | Animal; shared feeding engine |
| Weight | Yes | Optional | Animal; shared measurement contract |
| Length | Yes | No | Animal; snake capability |
| Shed | Yes | No | Animal; snake capability |
| Molt and premolt observation | No | Yes | Animal; spider contracts |
| Bath/soak | Yes | No | Animal; snake capability |
| Enclosure assignment/rehousing | Yes | Yes | Animal; neutral enclosure occupancy projection |
| Cleaning and water change | Yes | Yes | Enclosure |
| Configurable misting/watering | No by default | Yes where configured | Enclosure care with typed subject |
| Inventory, expenses, reminders, timeline | Yes | Yes | Existing shared subsystems |

Adding or changing a profile requires typed contracts, deterministic replay and projection
behavior, capability-policy tests, UI/accessibility tests, and compatibility-matrix coverage. An
unknown animal type, capability-profile version, or event contract fails safely under ADR-0005 and
ADR-0033; the system must not guess a closest profile.

## Projection and migration policy

The forward M5.5 relational migration adds an animal-type/profile discriminator to rebuildable
Animal read models and any required allow-listed indexes. Existing projection rows may be
deterministically backfilled as `snake.v1`, because that value is derived from the unchanged v1
registration contract rather than becoming a second source of truth. A full replay reaches the
same result.

Spider effective history uses additive projection fields or tables with deterministic rebuild
paths. Existing enclosure occupancy remains driven solely by effective Animal enclosure assignment.
Shared feeding, inventory, expense, reminder, attachment, and backup records retain their present
ownership and identifiers. No M0-M5 event, attachment, or operational record is rewritten.

## M6 read-side extension boundary

M6 search, reports, dashboards, charts, reference profiles, and explainable suggestions consume a
stable read model that includes animal type/profile identity and effective capability-specific
facts. Explicit inputs are common and type-specific feeding history, measurements, snake shed
history, spider molt history, reminder facts, enclosure care, and versioned species/life-stage
reference profiles. Analytics and prediction consumers must select applicable inputs by registered
capability and must not treat missing or inapplicable data as zero or overdue.

M5.5 does not implement those M6 consumers, curated husbandry guidance, predictions, search,
reports, dashboards, charts, or PWA expansion.

## Alternatives considered

- **Separate Snake and Spider aggregates and duplicated subsystems:** rejected because household,
  enclosure, feeding, inventory, reminder, and timeline behavior would diverge and cross-module
  coordination would multiply.
- **A generic EAV or arbitrary JSON capability model:** rejected because it weakens event typing,
  replay validation, UI safety, and compatibility scanning.
- **Rewrite v1 registration events with an animal type:** rejected because stored events are
  immutable and existing data is authoritative.
- **Keep snake assumptions until M6:** rejected because M6 analytics would otherwise be built on a
  known incorrect universal model.

## Consequences and compatibility

M5.5 is an additive compatibility milestone between M5 and M6. Existing snake replay and keeper
behavior are release blockers. New animal types can share the aggregate and infrastructure while
declaring a bounded, typed capability set; they do not gain sideways domain imports or private
access to another feature slice. New profile versions and event schemas follow normal registry,
upcaster, migration, correction, and safe-startup rules.

The main cost is an explicit capability check at application, projection, reminder, and
presentation boundaries plus a compatibility matrix for every supported profile. This cost is
preferred to implicit species conditionals scattered across templates and services.

## Governance and roadmap impact

This ADR amends implementation order and the original snake-centric assumptions in ADR-0001,
ADR-0004, ADR-0034, ADR-0035, and ADR-0038 without superseding their modularity, aggregate,
accessibility, release-gate, or scheduling decisions. M5.5 becomes a required milestone before M6.
Requirements R-047 through R-053 and the M5.5 roadmap checklist govern qualification. M6 through
M8 remain unstarted.
