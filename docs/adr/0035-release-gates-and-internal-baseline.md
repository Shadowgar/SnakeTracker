# ADR-0035: Separate Internal Baseline, Remote Readiness, and Production Launch

Status: Accepted
Acceptance date: 2026-08-04

## Context
Useful internal operation can be achieved before every public-deployment and final-product capability is complete, but labels must not weaken security gates.

## Decision
After Phase 4, permit an internal minimum usable baseline with secure local household access, animal profiles, feedings, measurements, sheds, enclosures, cleaning, timeline, and basic verified backup. It is not remote/public or final production approval. Remote access requires all RD-class controls through M7. Final launch requires M8 evidence and owner approval. Requirements are classified RB, RD, QT, or DC.

## Alternatives
One undifferentiated launch gate or calling the Phase 4 baseline production-ready.

## Tradeoffs
Multiple gates require clear deployment labeling and configuration enforcement.

## Future impact
Promoting deferred scope or relaxing a gate requires a superseding ADR and roadmap consequences.
