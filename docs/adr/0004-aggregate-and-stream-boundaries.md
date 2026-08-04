# ADR-0004: Define Aggregate and Stream Boundaries Explicitly

Status: Accepted
Acceptance date: 2026-08-04

## Context
Unclear ownership creates oversized aggregates, duplicate facts, and circular imports.

## Decision
Use Household, Animal, Enclosure, Inventory Item, Expense, Reminder Rule, Document, and Notification Preference streams. Animal owns current enclosure assignment. Husbandry and health are feature slices inside Animals and write through animal-owned ports. Read-side modules own no aggregates.

## Alternatives
Separate husbandry/health bounded contexts, a single household stream, or one stream per event category.

## Tradeoffs
Animal streams are broader but preserve animal-centric invariants. Cross-stream workflows require deliberate application coordination.

## Future impact
Stream splitting is reviewed at 10,000 events, replay/snapshot thresholds, or emerging independent workflow ownership.
