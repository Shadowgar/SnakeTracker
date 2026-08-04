# ADR-0019: Use SQLite FTS5 for Initial Search

Status: Accepted
Acceptance date: 2026-08-04

## Context
Global search spans animals, events, notes, health, inventory, expenses, and documents on a single-device deployment.

## Decision
Use an asynchronous FTS5 projection with generation-specific content and virtual tables. Search results are joined through household and current authorization. Rebuild, integrity, and optimization follow projection/SQLite operational rules.

## Alternatives
SQL `LIKE`, an external search service, or synchronous indexing.

## Tradeoffs
Results can lag and FTS storage requires maintenance; infrastructure remains lightweight.

## Future impact
An external search engine requires measured need and a migration ADR.
