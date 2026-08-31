# Owner Problem Triage

Status: Prospective roadmap mapping; no listed issue is implemented by this documentation update.

The [raw owner problem log](problemsfound.md) is preserved verbatim as the source record. This
companion maps every statement into the authoritative [milestone roadmap](../roadmap/milestones.md)
and [requirements traceability matrix](../requirements/traceability-matrix.md). Evidence remains
pending until the target milestone is implemented, qualified, owner-reviewed, and accepted.

## 1. Easier logout

> Logging out is not easy for the user. They must open their profile and click logout. It should be easier.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-065`; acceptance procedure `AT-M61-01`
- Status: **Planned — M6.1**

## 2. Mobile browser minimize/resume session persistence

> Minimizing the browser window on a mobile device and resuming should keep you logged in.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-066`; acceptance procedure `AT-M61-02`
- Status: **Planned — M6.1**

## 3. Calendar selected-day item navigation

> in calendar view, when clicking on the day box, a list pops up on the left that has the items for that day. The user should be allowed to click on those items to go to each indivdual item.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-067`; acceptance procedure `AT-M61-03`
- Status: **Planned — M6.1**

## 4. Calendar meaning and top legend

> in the calendar view, a mere number and a circle around it doesnt help much to tell the user what is going on that day. Also if we use color coded items or symbols, the "key" that tells users what those color are symbols mean need to be at the very top of the calendar. not at the bottom in which a user has to scroll past the calendar to the key to see what the calendar means.

- Target milestone: M6.1 — Final usability and correctness corrections
- Requirement: `R-068`; acceptance procedure `AT-M61-04`
- Status: **Planned — M6.1**

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
- Status: **Planned — M6.1**

The planned attribution is `© <current year> Paul Rocco`, linked appropriately to
`mailto:rocco.paul@gmail.com` and `https://github.com/Shadowgar/SnakeTracker`.

## 7. Useful inventory intelligence and physical recount

> inventory is useless. Example, I have a room full of items. I Can walk into that room and see a room full of items. So we made an inventory page that allows us to click on the page and see a page full of items. Whats the point? The inventory page should be somethign that the user needs. Something that the user can at a glance see what they have and if they are low on stock and need to reorder. or if they have too much of something cuase they are no longer using the items. The page has to defeat the reason of just walking into a room and "seeing there are items we own." It should provide enough information that the person goes to the page to analyze their stock levels and make informed decisions on what to do when they go into the room. There also should be some method of makign the user do a recount to make sure their items are correctly accounted for.

- Target milestone: M6.5 — Inventory intelligence and cost tracking
- Requirements: `R-070`–`R-072` and `R-076`; acceptance procedures `AT-INVINT-01`–`AT-INVINT-03` and `AT-INVINT-06`
- Status: **Planned — M6.5**

## 8. Inventory-linked expenses and consumption cost

> Also for expenses, this should tightly tie into inventory. Every item should be labeled with prices that the user paid and should cross reference with eachother. That should also show how much the user spent on items and how much of that item has been used to project their spending verse the actual cost of consumption so they can determine if they need to spend less in the future, or more.

- Target milestone: M6.5 — Inventory intelligence and cost tracking
- Requirements: `R-073`–`R-076`; acceptance procedures `AT-INVINT-04`–`AT-INVINT-06` and architecture review `AR-INVINT-01`
- Status: **Planned — M6.5**

The roadmap distinguishes cash spending, inventory value, and consumption cost. Purchase history or
cost lots are required; a single mutable price is insufficient. The exact deterministic costing
policy is deliberately deferred to M6.5 architecture/domain review and an ADR if required.

## Milestone sequence and status boundary

The roadmap order is M6 UX Passes 1–4, M6.1, final M6 qualification and explicit owner acceptance,
M6.5, M7, M8, then M9. This triage records planned work only: it does not complete M6, authorize
PR #8 merge, qualify Raspberry Pi deployment, enable public sharing, or begin any implementation.
