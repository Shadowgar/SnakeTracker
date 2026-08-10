# Architecture Amendment Evidence: M4 Shed Correction Contract

- Decision: narrow event-catalog amendment, no new ADR required
- Acceptance date: 2026-08-07
- Authority: SnakeTracker owner Phase 4 implementation authorization
- Baseline commit: `bb3ab394a1487943424dad6d7544995c71156c98`
- Amendment branch: `phase4/animal-care`
- Review status: Accepted for implementation

## Approved change

Add `animal.shed_corrected` v1 beside the accepted `animal.shed_recorded` contract. The correction
payload references `target_event_id` and contains the replacement shed facts. It is permitted only
for a same-stream, same-household shed target and is registered as correctable, voidable, and
reinstatable.

## Why an explicit contract is required

M4 requires shed records to be corrected safely. A void only removes an effective record and cannot
express the corrected observed time, blue/in-shed state, completion, quality, or notes. A typed
replacement preserves immutable history and gives projections deterministic apply, reverse, and
reinstate behavior.

## Consequence review

- Aggregate, stream, envelope, subject, correction-platform, projection-generation, and database
  ownership decisions are unchanged.
- Existing `animal.shed_recorded` events are never rewritten. Replay applies later correction events
  in stream order; an older release fails closed when it encounters the new contract.
- The effective animal timeline supersedes the target while the correction is active, restores the
  predecessor on reversal/void, and reapplies it on reinstatement.
- No schema migration, upcaster, external integration, remote deployment, or Raspberry Pi
  qualification change follows from this catalog addition.
- Tests must cover payload validation, target validation, replay, effective state, void, reinstate,
  and historical-record compatibility before the contract is enabled in production composition.

## Reproduction

From the repository root, run:

```sh
uv run pytest tests/unit/scripts/test_architecture_freeze.py
uv run python scripts/quality/verify_architecture_freeze.py
make check
```