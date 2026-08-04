# ADR-0033: Publish a Release Compatibility Matrix

Status: Accepted
Acceptance date: 2026-08-04

## Context
Older code must not partially interpret newer schemas, events, projections, plugins, or backups.

## Decision
Every release declares application/build, relational schema range, readable/writable event contracts, upcasters, projection generations, plugin API/packages, backup-manifest versions, runtime requirements, and downgrade class. Startup performs a conservative read-only scan and enters restricted recovery mode on unknown newer or missing required compatibility.

## Alternatives
Best-effort startup or documentation-only version notes.

## Tradeoffs
Release automation and retained compatibility fixtures are mandatory.

## Future impact
Compatibility evidence is a release gate through M8.
