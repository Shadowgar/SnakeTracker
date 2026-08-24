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
