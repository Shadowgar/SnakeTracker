# Architecture Amendment Evidence: Phase 2 Household Events

- Decision: ADR-0037
- Acceptance date: 2026-08-05
- Authority: SnakeTracker owner instruction after identifying the Phase 2 ordering conflict
- Status: Accepted
- Branch: `phase2/identity-household`

The owner approved bringing forward only the permanent household event infrastructure necessary
for atomic initial-household and owner bootstrap. Temporary relational household truth, deferring
bootstrap, and bringing the general Phase 3 event platform forward were rejected.

The amendment preserves ADR-0002, ADR-0015, the established event envelope and contract names, and
Phase 3 replay compatibility. It authorizes no animal events or other general Phase 3 capability.

Verification commands:

```sh
uv run python scripts/quality/verify_docs_links.py
uv run python scripts/quality/verify_architecture_freeze.py
uv run pytest tests/unit/scripts/test_architecture_freeze.py
```
