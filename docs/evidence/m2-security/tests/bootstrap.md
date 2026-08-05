# AT-AUTHZ-01 and AT-EVT-HH-01 Bootstrap Evidence

- Requirements: R-015, R-043
- ADRs: ADR-0002, ADR-0005, ADR-0011, ADR-0012, ADR-0015, ADR-0037
- Threat controls: TM-04, TM-09, TM-20
- Result: Pass

`tests/integration/test_household_bootstrap.py` proves that one SQLite transaction writes the user,
`household.created` and `household.owner_added` events at stream versions 1 and 2, event subjects,
the household/current-membership projection, completed idempotency result, and security audit.
Injected projection failure rolls back every record. Equivalent retry returns the stored result;
mismatched retry conflicts. Unknown household contracts force restricted recovery mode.

`tests/unit/domains/test_household_events.py` proves stable contract identities, checksums,
deserialization, contiguous replay, and gap rejection. Phase-scope tests continue to exclude animal
events and the general Phase 3 event platform.
