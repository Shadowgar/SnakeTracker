# AT-AUTHZ-01 and AT-EVT-HH-01 Bootstrap Evidence

- Source revision: `25d52a34ce3cb343d1678de75118863d844d80b5`
- Execution date: 2026-08-06
- Environment: x86_64 WSL2 laptop, Python 3.13.14, SQLite via the pinned `uv.lock`
- Reviewer: Codex automated verification; owner review through PR #3
- Requirements: R-015, R-043
- ADRs: ADR-0002, ADR-0005, ADR-0011, ADR-0012, ADR-0015, ADR-0037
- Threat controls: TM-04, TM-09, TM-20
- Result: Pass

Reproduce from the repository root with:

```sh
uv sync --frozen
uv run pytest tests/integration/test_household_bootstrap.py \
  tests/unit/domains/test_household_events.py \
  tests/unit/bootstrap/test_compatibility.py -q
```

`tests/integration/test_household_bootstrap.py` proves that one SQLite transaction writes the user,
`household.created` and `household.owner_added` events at stream versions 1 and 2, event subjects,
the household/current-membership projection, completed idempotency result, and security audit.
Injected projection failure rolls back every record. Equivalent retry returns the stored result;
mismatched retry conflicts. Unknown household contracts force restricted recovery mode.

`tests/unit/domains/test_household_events.py` proves stable contract identities, checksums,
deserialization, contiguous replay, and gap rejection. Phase-scope tests continue to exclude animal
events and the general Phase 3 event platform.
