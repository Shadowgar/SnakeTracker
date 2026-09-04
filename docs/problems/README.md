# Owner Problem Triage

Status: M6 owner-accepted and merged; M6.5 architecture/domain proposal prepared. Later
milestones remain prospective.

The [raw owner problem log](problemsfound.md) is preserved verbatim as the source record. This
companion maps every statement into the authoritative [milestone roadmap](../roadmap/milestones.md)
and [requirements traceability matrix](../requirements/traceability-matrix.md). M6.1 implementation
evidence is [here](../evidence/m6-product-experience/m6.1-usability-corrections/README.md); M6 owner
acceptance and PR #8 merge are complete.

## 1. Easier logout

> Logging out is not easy for the user. They must open their profile and click logout. It should be easier.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-065`; acceptance procedure `AT-M61-01`
- Status: **Accepted in M6**

## 2. Mobile browser minimize/resume session persistence

> Minimizing the browser window on a mobile device and resuming should keep you logged in.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-066`; acceptance procedure `AT-M61-02`
- Status: **Accepted in M6**

## 3. Calendar selected-day item navigation

> in calendar view, when clicking on the day box, a list pops up on the left that has the items for that day. The user should be allowed to click on those items to go to each indivdual item.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-067`; acceptance procedure `AT-M61-03`
- Status: **Accepted in M6**

## 4. Calendar meaning and top legend

> in the calendar view, a mere number and a circle around it doesnt help much to tell the user what is going on that day. Also if we use color coded items or symbols, the "key" that tells users what those color are symbols mean need to be at the very top of the calendar. not at the bottom in which a user has to scroll past the calendar to the key to see what the calendar means.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-068`; acceptance procedure `AT-M61-04`
- Status: **Accepted in M6**

## 5. Animal profile photo, album, video, and public gallery

> Each animal should allow a user to upload a photo for a profile picture and a seperate upload section to allow uploading multiple pictures and videos for a "Album" that they can share online to the public. allowing public to go to something like tracker.theroccos.us/&lt;user&gt;/&lt;animal-id&gt; to view the album. Or a General Gallery for the user that shows a listing of all their animals and allows the user to click on each animal to see their album.

- Target milestone: M9 — Public profiles, albums, and media sharing
- Requirements: `R-077`–`R-081`; acceptance procedures `AT-PUB-01`–`AT-PUB-05` and architecture review `AR-PUB-01`
- Status: **Planned — M9**

The owner's example communicates the desired visitor experience, not a decision to expose internal
identifiers. M9 design must choose explicit public identifiers and pass its opt-in privacy, media
security, capacity, and no-leakage gates before public access is enabled.

## 6. Copyright and author footer

> Bottom of the website should be a copyright notice. and the Author's name. with email. "Paul Rocco" &lt;rocco.paul@gmail.com&gt; With the github link.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-069`; acceptance procedure `AT-M61-05`
- Status: **Accepted in M6**

The planned attribution is `© <current year> Paul Rocco`, linked appropriately to
`mailto:rocco.paul@gmail.com` and `https://github.com/Shadowgar/SnakeTracker`.

## 7. Useful inventory intelligence and physical recount

> inventory is useless. Example, I have a room full of items. I Can walk into that room and see a room full of items. So we made an inventory page that allows us to click on the page and see a page full of items. Whats the point? The inventory page should be somethign that the user needs. Something that the user can at a glance see what they have and if they are low on stock and need to reorder. or if they have too much of something cuase they are no longer using the items. The page has to defeat the reason of just walking into a room and "seeing there are items we own." It should provide enough information that the person goes to the page to analyze their stock levels and make informed decisions on what to do when they go into the room. There also should be some method of makign the user do a recount to make sure their items are correctly accounted for.

- Target milestone: M6.5 — Inventory intelligence and cost tracking
- Requirements: `R-070`–`R-072` and `R-076`; acceptance procedures `AT-INVINT-01`–`AT-INVINT-03` and `AT-INVINT-06`
- Status: **Architecture proposed — M6.5 not implemented**

## 8. Inventory-linked expenses and consumption cost

> Also for expenses, this should tightly tie into inventory. Every item should be labeled with prices that the user paid and should cross reference with eachother. That should also show how much the user spent on items and how much of that item has been used to project their spending verse the actual cost of consumption so they can determine if they need to spend less in the future, or more.

- Target milestone: M6.5 — Inventory intelligence and cost tracking
- Requirements: `R-073`–`R-076`; acceptance procedures `AT-INVINT-04`–`AT-INVINT-06` and architecture review `AR-INVINT-01`
- Status: **Architecture proposed — M6.5 not implemented**

The roadmap distinguishes cash spending, inventory value, and consumption cost. Purchase history or
cost lots are required; a single mutable price is insufficient. The exact deterministic costing
policy is deliberately deferred to M6.5 architecture/domain review and an ADR if required.
The [architecture proposal](../plans/2026-09-04-m6.5-inventory-intelligence-architecture.md) and
[ADR-0042](../adr/0042-inventory-purchases-fifo-and-quantity-policy.md) now recommend the policy;
the ADR remains Proposed pending owner review.

## 9. Normal phone profile-photo upload

> A normal modern phone photo (5.7 MB, 3072×4080) could not be uploaded as an animal profile picture because Care Keeper reported that it was too large. Users should not have to manually resize ordinary phone photos before uploading them.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-082`; acceptance procedure `AT-M61-06`
- Status: **Accepted in M6**

This is a newly discovered existing-feature usability/correctness issue. The known image must pass,
but implementation must justify bounded file/pixel/resource limits, validate decoded content,
normalize orientation, generate web-appropriate derivatives, strip unnecessary EXIF/GPS metadata,
and preserve attachment authorization and Raspberry Pi safety. Future M9 public media must reuse or
deliberately extend this privacy-safe boundary rather than expose raw metadata.

## Milestone sequence and status boundary

The roadmap order is M6 UX Passes 1–4, M6.1 (six owner issues), final M6 qualification/acceptance,
M6.5, M7, M8, then M9. M6 and PR #8 are complete. M6.5 design does not qualify M7 Raspberry Pi
deployment/recovery, authorize M8 release qualification, or enable M9 public sharing.
