# ADR-0022: Use Trusted, Startup-Loaded Plugins

Status: Accepted
Acceptance date: 2026-08-04

## Context
Future extensions need stable registration without introducing an unbounded runtime marketplace.

## Decision
Plugins are verified trusted Python packages and are not sandboxed. They declare API ranges, signatures, event ownership, migrations, upgrade/rollback support, capabilities, and handler-retention policy. Missing/incompatible required handlers force restricted recovery mode. A plugin cannot be removed while historical events require it.

## Alternatives
No plugin seams, runtime untrusted plugins, or microservices for every extension.

## Tradeoffs
Administrators assume the risk of privileged plugin code; compatibility management is permanent.

## Future impact
An untrusted marketplace requires process isolation and a separate security architecture.
