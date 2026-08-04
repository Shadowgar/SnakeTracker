# ADR-0020: Use a Server-Rendered Strict-CSP UI

Status: Accepted
Acceptance date: 2026-08-04

## Context
The target favors low resource use and simple maintenance while demanding polished interactions and XSS resistance.

## Decision
Use Jinja2, Bootstrap 5, HTMX, Alpine CSP build, and Chart.js. Use external scripts/styles, no generated JavaScript in templates, no `unsafe-inline`/`unsafe-eval`, CSP reporting, and regression tests. Alpine handles only small local state.

## Alternatives
React/Vue SPA, unenhanced server pages, or permissive CSP.

## Tradeoffs
Complex client state is intentionally constrained and third-party components must be CSP compatible.

## Future impact
Frontend-framework adoption needs overwhelming measured benefit and a superseding ADR.
