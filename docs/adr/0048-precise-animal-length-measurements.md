# ADR-0048: Exact length measurement representation and consumer semantics

Status: Proposed
Decision date: 2026-10-01

## Context

Length v1 uses integer millimetres end to end. Reasonable decimal mm/cm/in inputs cannot all fit
that contract exactly. [ADR-0005](0005-event-contracts-and-evolution.md) protects existing events;
the application's scaled-integer [weight implementation](../../src/snaketracker/application/weight_measurements.py)
provides an exact-storage precedent. This ADR owns all length precision/unit rules.

## Decision

### Exact representation and validation

Retain `animal.length_recorded` / `animal.length_corrected` v1 unchanged. Add v2 storing canonical
positive integer `length_um` (micrometres), plus `entered_value_scaled` (positive integer),
`entered_scale` (integer decimal-place count), and `entered_unit` (`mm`, `cm`, `in`). The scaled
value divided by `10 ** entered_scale` retains the entered decimal magnitude and fractional
precision, including trailing fractional zeros; incidental whitespace/leading zeros are not data.
The correction also retains the existing target reference.

| Unit | Maximum entered decimal places | Exact canonical micrometres per unit |
|---|---|---|
| mm | 1 | 1,000 |
| cm | 2 | 10,000 |
| in | 2 | 25,400 |

Canonical precision is one micrometre. Scaled integers represent every accepted increment exactly,
without decimal database portability concerns. Precisely specified decimal-mm storage could also
work, but integer micrometres follows the existing weight pattern and makes equality unambiguous.
Binary floating point is never authoritative input parsing, conversion or storage.

Parse plain finite decimal input using exact decimal/integer arithmetic; reject unsupported units,
exponents, excessive fractional digits (even extra zeros), nonpositive values and malformed numbers.
Validate **at commands and event deserialization** that
`length_um * 10 ** entered_scale == entered_value_scaled * unit_um` exactly, with the unit's allowed
scale and integer types; disagreement is invalid, not silently repaired. After conversion, physical
bounds are 100–10,000,000 micrometres inclusive (0.1–10,000 mm). Never truncate or round into range.

| Input | Canonical value | Result |
|---|---|---|
| 48.5 in | 1,231,900 µm | Accepted; entered unit/scale retained |
| 48.5 cm | 485,000 µm | Accepted; distinct from the inch input |
| 48.5 mm | 48,500 µm | Accepted |
| 12.25 cm | 122,500 µm | Accepted |
| 0.5 mm | 500 µm | Accepted |
| 12.25 mm | — | Rejected: more than one decimal place, no rounding |

### Corrections and effective history

A correction appends a complete valid v2 value/unit tuple, whether fixing the number, unit, or both.
Number-only correction preserves the chosen unit; unit-only correction preserves the entered number
but **recomputes** canonical magnitude (48.5 in → 48.5 cm is 1,231,900 → 485,000 µm). If both change,
validate the replacement tuple afresh. Changing a viewing preference is not a historical correction.
Show old/new number and unit for confirmation; do not change only a unit label on stored magnitude.

Mixed effective calculations normalize v1 as `length_mm * 1000`, never rewriting/upcasting stored v1.
A v2 correction can target v1; correction chains, void and reinstatement use the existing effective
history rules under [ADR-0006](0006-corrections-and-compensation.md). Reminders must retain the
qualifying effective fact/source identity and one-time override consumption consistently through
these transitions; new classes cannot make a historical corrected fact disappear.

### Display, analytics, charts and reporting

Timeline/history and current facts display effective entered value/precision/unit; v1 remains mm.
Any keeper-preferred conversion is labelled with its unit and a viewing approximation where needed,
without altering original input. Analytics combines v1/v2 using canonical integer micrometres.
Chart datasets use one numerical unit, **millimetres**, derived exactly from micrometres before
final plotting-number conversion; axis labels are mm, never mixed cm/in/mm under the same series.
Tooltips may additionally show the original/preferred value with an explicit unit. Floating point
in final browser rendering is presentation only, never a saved or replayed authority.

PR 1 explicitly delivers a precise measurement report/CSV with effective measurement time/kind,
canonical integer micrometres and entered value/unit/scale (v1 labelled mm), preserving correction,
void and reinstatement semantics. The existing care CSV contains titles/notes rather than numeric
measurements: preserving it alone does not prove precise export support. Human reports use labelled
original/preferred units; machine export never drops scale or silently rounds. The complete
[PR 1 consumer matrix](../plans/2026-10-01-extensible-animal-and-species-platform.md#length-v2-consumer-qualification)
is the qualification inventory, including reminders, charts, reports, search applicability and replay.

## Consequences and gates

All consumers support v1/v2 indefinitely. Forms expose decimal entry and unit accessibly; browser
step hints are not the server validator. `AT-MEASURE-01` and `AT-PRODCOMP-01` qualify inputs, mismatched
payload rejection, effective history and isolated production replay before deployment. Event changes
do not automatically require Alembic under [ADR-0026](0026-migration-and-rollback.md): current Animal
identity projection has no length column. Review projection contract allowlists/handlers separately;
use a relational migration only if actual persisted schema changes require one.
