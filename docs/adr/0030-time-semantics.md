# ADR-0030: Store UTC and Report in Household Time

Status: Accepted
Acceptance date: 2026-08-04

## Context
Real-world husbandry times differ from recording times, and daylight-saving transitions make naive timestamps ambiguous.

## Decision
Persist timezone-aware UTC at microsecond precision. Store server `recorded_at` and user/business `occurred_at`. Interpret wall times with the household IANA timezone and explicit DST ambiguity handling. Display and group calendar reports in household time by default. Reject over-five-minute future skew unless an authorized import policy applies. Never order by timestamps.

## Alternatives
Naive local timestamps or UTC-only user experience.

## Tradeoffs
Imports and timezone changes require explicit semantics.

## Future impact
Organization/user-specific reporting timezones require a later policy ADR.
