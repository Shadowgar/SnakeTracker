# M6.6 — owner iPhone, VoiceOver and keyboard acceptance

**Status: pending.** No physical-device or screen-reader session was performed for
this package. Allow about 15–20 minutes once the fixture is ready. Use the **owner's real
iPhone in Safari**, not desktop mobile emulation.
The [November 8 deployed browser results](../roadmap-continuation-20261107/production-retry-20261108.md)
and [PR34 geometry/axe qualification](../plant-detail-layout-20261107/README.md)
are reused, not rerun. [M6.6-B's October 5 acceptance](../m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance)
remains valid; it does not supply device evidence for the later changed screens.

## Record before starting

| Field | Owner observation |
| --- | --- |
| Tester and date/time/timezone | Pending |
| iPhone model; iOS/Safari version | Pending |
| Portrait/landscape; text size and display zoom | Pending |
| Production or isolated-fixture URL; verified build | Pending — target `cf772cf8348f3eeb2ec069754b585bffd6c926cf` |
| VoiceOver enabled; relevant verbosity/navigation settings | Pending |
| Keyboard used; hardware connection and Full Keyboard Access setting, if applicable | Pending |

Use only the owner's authorized household for production browsing. There, open
screens, edit form values, preview and cancel; do **not** confirm schedules, save
watering/mode/plant changes, correct/void history, remove records or generate care
events for testing. Preserve existing records and schedules.

Confirmation and error tests require a **separate functioning fictional fixture**
on the qualified build, reachable safely from the same iPhone, with no production
database, media, credentials or keys. Fixture availability/access is **pending**.
If unavailable, leave those rows Not run; do not substitute production writes or
publicly expose a fixture. This task does not prepare, import or serve one.

## Short walkthrough

For each row record **Pass / Fail / Not run**, environment, observation and an
evidence/issue link. An automated pass does not complete a device row.

| ID | Action and expected result | Result |
| --- | --- | --- |
| P1 | Open an existing Animal, Care and Guides & Species Reference; go to its enclosure and back. Titles, selected navigation and back paths identify the correct Animal/enclosure; history remains reachable. | Pending |
| P2 | Open Directory. Its empty-query screen says **Start with a name**; follow an existing linked species to its detail and an already available Care Guide. Read source/provenance, version, cautions and any **Single source / Sources differ** labels. Reference advice remains distinct from keeper records. An unavailable guide/Natural History section is an honest unavailable state, not a failed publication. | Pending |
| P3 | Open **Smart care setup**. Inspect a reviewed choice where available and **Manual setup** when guidance is missing. Check source/life-stage applicability and shared-enclosure scope. Inspect interval/due date, choose **Preview schedule**, compare current/proposed values and timezone, then **Edit again** and **Skip for now**. No production schedule changes. | Pending |
| P4 | **Isolated fixture only:** complete one reviewed feeding choice and one manual/no-guidance setup using **Confirm schedule change** or **Confirm and create schedule**. Confirm only the selected schedule changes; return to Care/Today/Calendar to inspect the displayed result. Do not create care events to make a schedule due. Without the fixture, mark Not run. | Pending |
| P5 | Open an existing enclosure's **Enclosure mode**, **Plants**, and **Maintenance schedules and history**. Read Bioactive status and the separation of cleaning, water changes and plant watering. Open a plant without saving mode or changing occupancy. | Pending |
| P6 | On Plant Detail, check the photo is bounded and undistorted, name/species/status appear near the top, and creator/source/license links remain readable and open correctly. Use **Watering & history**, **Set watering schedule**, and **Review, correct or void watering history**; inspect then return without submitting. **Save watering**, Edit and Remove remain identifiable. Use fixture cases for missing image and long names. | Pending |
| P7 | Repeat the key Animal, guide, Smart Care edit/preview and Plant screens in portrait and landscape with enlarged text. No sideways scrolling, clipped text or unreachable action; the software keyboard and fixed navigation do not obscure the active field or the means to continue/cancel. Emulated 320/390 px results remain separate. | Pending |

The annotated Swiss Cheese plate remains a separate content issue. Preserve its
attribution; this walkthrough does not replace it.

## VoiceOver and keyboard pass

Use the same iPhone/screens and record actual announcements and focus. Use the
isolated fixture for every action that commits a change.

| ID | Expected behavior | Result |
| --- | --- | --- |
| A1 | Navigate by headings and links through Animal, enclosure, Directory/guide, Smart Care and Plant. Page identity and section headings are meaningful; reading/focus order follows the task, without repeated decorative content or a navigation loop. | Pending |
| A2 | Reference photos have meaningful species-reference names; creator/license/source links are distinguishable. Status and source disagreement are understandable without relying on color or the image. A missing-image decoration does not become an unexplained actionable control. | Pending |
| A3 | Interval, due date/time, applicability checkbox and plant watering fields expose their labels, values, requirements and state. VoiceOver can enter/edit values with the iPhone keyboard and return to navigation without losing the intended field. | Pending |
| A4 | Activating **Watering & history**, opening a guide/source, and moving edit → preview → **Edit again** leaves the relevant content and actionable controls discoverable. No focus trap or unexplained jump to unrelated navigation. Source/context, old/new schedule values and the exact Confirm action are announced before an isolated confirmation. | Pending |
| A5 | **Isolated fixture only:** leave a required value invalid, then correct it. Error identification is discoverable/announced and associated with the field; entered values are retained where appropriate. Confirm and cancel controls have unambiguous names and work with VoiceOver. Destructive actions remain distinguishable. | Pending |
| K1 | With the iPhone software keyboard, numeric/date entry and dismissal leave the field and next action accessible. If using a hardware keyboard, record its access settings and verify forward/backward traversal, visible focus, activation and return/cancel without touch or traps. **No hardware-keyboard result may be claimed if no keyboard was tested.** | Pending |

## Record the outcome without closing the milestone

- Device walkthrough: **Pending**. VoiceOver: **Pending**. Keyboard: **Pending**.
- Record each failure with row ID, page, exact observed/expected behavior, device
  settings and a privacy-safe evidence reference. Skipped cases remain **Not run**; unresolved failures remain open.
- Owner disposition: **Pending** — accept the demonstrated manual scope, request
  corrections, or leave identified checks open. This record does not invent the
  missing historical M6.6-A acceptance, authorize Frog/Natural History publication,
  or itself grant final M6.6 acceptance.
