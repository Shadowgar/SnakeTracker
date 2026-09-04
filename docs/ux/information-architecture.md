# UX Information Architecture

## Product principles

Care Keeper minimizes taps for frequent keeper work, keeps urgent care facts visible, and uses
progressive disclosure for clinical and administrative detail. Mobile is primary; desktop adds
density rather than a different mental model. Trusted profiles support Snake, Spider, Lizard, and
Scorpion collections; screens derive relevant actions from capabilities rather than species text.

## Primary navigation

Mobile bottom navigation:

1. Today
2. Animals
3. Timeline
4. Inventory
5. More

Desktop navigation additionally exposes Enclosures, Reports, and Administration. Global search remains reachable from every primary view.

## Today dashboard

Priority order:

1. Overdue medication and health actions
2. Animals losing weight or repeatedly refusing food
3. Today's and upcoming feedings
4. Cleaning, water, and measurement tasks
5. Shedding animals
6. Recent activity
7. Collection statistics

Quick actions open focused forms for feeding, measurement, shed, cleaning, health observation, and inventory receipt. Asynchronous statistics show freshness when lag can affect interpretation.

## Animal information architecture

Animal profile sections:

- Overview: photo, identity, status, enclosure, urgent facts
- Timeline: effective chronological history with correction markers
- Feeding
- Growth: capability-applicable weight and length tables/charts
- Capability-applicable shed or molt history
- Health
- Documents/photos
- Profile and lifecycle settings

Husbandry and health remain coherent feature slices within one animal experience. Corrections display the current effective value and offer authorized access to history.

## Enclosures, inventory, reports, and administration

- Enclosure views show profile, projected occupants, last cleaning/water change, and due state.
- Inventory emphasizes balance, expiry, reorder status, and auditable movements.
- Reports provide accessible tabular alternatives to every chart and export only authorized data.
- Administration contains household users/roles, backup health, dead letters, projection health, plugins, security audit, and compatibility diagnostics.

### Proposed M6.5 Inventory experience

Pending owner approval of ADR-0042, Inventory evolves from a list-first screen to this mobile-first
hierarchy:

1. Needs attention: owner-threshold reorder state, count due/not verified, and shortest supported
   duration.
2. Stock snapshot: current available quantity, known value, and explicit unknown-cost stock.
3. Reorder and verification: evidence plus direct Add purchase / Start count actions.
4. Usage and purchasing: 30/90-day use, explainable duration, unused observations, and recent
   Purchases.
5. All items: searchable/filterable item list after the decision-support summary.

Item detail combines current quantity/policy, rate/duration explanation, last count, Purchase lots,
consumed/current value, and immutable movements. Actions are Add purchase, Use inventory, Count
stock, Adjust stock, Edit policy, and Archive/Restore.

A phone count selects Full, Category, Cycle, or One item, then shows one item's unit and expected
quantity with a large actual-quantity input and thumb-reachable Save & next. Each save is an
independent concurrency-safe count fact; review permits appended correction. Desktop uses the same
hierarchy with a denser table/review pane. Expenses distinguishes linked Supply purchases from
Other expenses and never creates a second editable Expense for a Purchase.

Rates, duration, stock value, unknown cost, and spending estimates always display source window,
currency, freshness, and estimate/unavailable language where material. This section is a wireframe-
level proposal only; no M6.5 UI is implemented.

## Interaction and accessibility rules

- Minimum touch target: 44 by 44 CSS pixels.
- Critical actions remain thumb reachable on small screens.
- Forms use persistent labels, field help, inline errors, and a focused error summary.
- HTMX updates announce meaningful changes through scoped live regions.
- Keyboard order follows visual order and focus is deliberately restored after swaps/modals.
- Destructive or compensating actions require clear consequence summaries.
- Color is never the only signal; charts have tables or summaries.
- Light/dark themes meet WCAG 2.2 AA contrast.
- Reduced-motion preference is respected.

## Concurrency and offline behavior

Conflicts preserve allowed form data, explain that the record changed, show refreshed context, and offer compare/resubmit without silent overwrite. Online status is explicit. Offline v1 shows cached shell/offline guidance and performs no writes. Draft persistence is denied unless a specific low-sensitivity form is reviewed and allow-listed; drafts expire and clear on submit, logout, role loss, or user action.

## Responsive states

Every screen defines loading, empty, partial/stale, permission-denied, recoverable error, offline, and success states. Skeletons must not obscure meaning, and failures must remain actionable without relying on developer terminology.
