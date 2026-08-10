# Phase 4 Keeper UX Correction Addendum

**Status:** Owner-required Phase 4 correction, authorized August 10, 2026.

## Scope

This addendum refines the browser presentation of the existing Phase 4 animal-care slice. It does
not change aggregate ownership, event contracts, migrations, authorization, attachment storage,
backup behavior, or effective-history semantics.

The keeper experience will:

- identify animals with name, species, status, and the selected immutable profile photo on animal
  listings;
- make the animal profile a concise overview with care-history links and focused record actions;
- place feeding, weight, length, shed, and bath entry on dedicated authenticated pages while
  retaining the existing protected command endpoints;
- present entered feeding, weight, and length facts with their units and human-readable care-event
  descriptions;
- use the authoritative effective history so corrections replace the displayed effective facts and
  voided records are omitted from ordinary keeper history;
- keep immutable event identifiers, correlation and causation data, and correction controls in a
  collapsed technical-audit disclosure; and
- retain keyboard, screen-reader, responsive desktop, and responsive phone behavior without inline
  or generated JavaScript.

## Test-driven sequence

1. Add browser tests for listing identity/photo presentation and the concise overview.
2. Add route and form tests for each focused care-entry page, including authentication and
   validation behavior.
3. Add presentation tests for actual feeding and measurement values, corrected effective values,
   void exclusion, readable event descriptions, and the collapsed technical audit.
4. Implement only the presentation adapter, templates, and responsive styles necessary to satisfy
   those tests.
5. Run the complete M4 qualification suite and refresh the evidence package and PR #5.

## Explicit exclusions

Charts, analytics, reports, global search, inventory, expenses, reminders, notifications,
dashboard statistics, animal health workflows, remote access, and Raspberry Pi deployment remain
out of scope. No existing Phase 2 or Phase 3 event or relational data will be rewritten.
