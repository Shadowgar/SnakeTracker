# ADR-0034: Make Mobile Accessibility a Release Criterion

Status: Accepted
Acceptance date: 2026-08-04

## Context
Keepers frequently record care on mobile devices, sometimes under time pressure, and inaccessible flows undermine the product.

## Decision
Target WCAG 2.2 AA, 44×44 touch targets, semantic HTML, keyboard access, visible focus, error summaries, HTMX live-region/focus behavior, reduced motion, contrast-compliant themes, and table/summary alternatives for charts. Design mobile-first with progressive desktop density.

## Alternatives
Desktop-first design or automated accessibility scanning alone.

## Tradeoffs
Manual assistive-technology testing and reusable accessible components are required.

## Future impact
Every critical journey needs automated and manual evidence before its release milestone.
