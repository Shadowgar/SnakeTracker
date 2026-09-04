# Authorized FTS5 Search

The search suite proves household scoping, financial-capability filtering, Unicode tokenization,
query limits, correction/void/reinstatement behavior, deterministic rebuilds, and allow-listed
physical identifiers. Keeper snippets exclude raw event IDs and contract-version metadata.

Reproduce with `uv run pytest -q tests/integration/test_search.py
tests/unit/infrastructure/test_search_projection.py`.
