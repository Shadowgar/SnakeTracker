# Architecture and Milestone Evidence

Evidence is retained by milestone:

```text
docs/evidence/
├── m0-architecture/
├── m1-platform/
├── m2-security/
├── m3-event-integrity/
├── m4-internal-baseline/
├── m5-operations/
├── m5.5-multispecies-foundation/
├── m6-product-experience/
├── m7-recovery-compatibility/
└── m8-production/
```

Each milestone may contain `tests/`, `security/`, `performance/`, `accessibility/`, `operations/`, `screenshots/`, and `approvals/` as applicable.

## Evidence record requirements

Every record states:

- Requirement and acceptance-test IDs
- Release/build and source revision
- UTC execution time and operator/automation identity
- Exact documented command or procedure reference
- Environment and dataset manifest
- Raw output or durable artifact location
- Result and deviations
- Reviewer and approval date

Generated evidence must be reproducible from a checked-in command, test, benchmark manifest, or numbered runbook procedure. Handwritten claims without source revision and reproduction method do not satisfy a mandatory gate. Sensitive outputs are redacted or stored in an access-controlled external evidence store with a checked-in manifest reference.

Evidence is append-oriented. Superseded evidence remains identifiable and linked to the superseding run. M0 contains the approved architecture-package inventory and owner approval.
