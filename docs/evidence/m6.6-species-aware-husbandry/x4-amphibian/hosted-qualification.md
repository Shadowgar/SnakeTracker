# Hosted qualification follow-up

Initial head: `83de214cd6c0fb0b07fbfaa23a616a198101f4b2`.
[Quality run 187](https://github.com/Shadowgar/SnakeTracker/actions/runs/40176834721)
ran the unchanged full gate. Pytest completed in 357.88s: **1,555 passed, four failed**,
with reported combined coverage 92.95%. Because pytest failed, later gate stages did not run.
Container and GitGuardian passed; Codex review completed on this head with no findings.

The failures were pre-X4 fixture expectations, not runtime failures:

- The reference-only refresh test used Amphibian to represent a group unsupported by the provider.
  Amphibians are now enabled. The test now retains blank/Fish exclusion and explicitly verifies
  that an Amphibian refresh is invoked and applied using ordered synthetic source revisions.
- Web and worker startup tests still reject Amphibian registrations encoded as v2, before mutable
  startup. Their expected diagnostic is now invalid payload, because amphibian.v1 is a known
  profile that requires registration v3. A separate Fish v1 case retains unknown-identity rejection.
  Existing privacy, normal-route exclusion, journal-mode and exact database-byte checks remain.
- The future-extension isolation test now requires exactly the approved five profiles/groups.
  Dog, Fish and colony workflows remain outside the production registry.

Focused command:

```sh
uv run pytest -q tests/unit/domains/test_future_care_extensions.py tests/integration/test_x1_conventional_startup.py tests/integration/test_species_directory.py -k 'future_examples or incompatible_identity or selected_taxon_refreshes'
```

Result: **16 passed, 28 deselected in 7.09s**. An intermediate positive-refresh fixture omitted
source revision ordering and correctly retained the prior overlay; explicit source clocks fixed
that fixture without changing application code or weakening the expected refreshed content.

The follow-up commit changes only tests and evidence. Product source, assets and screenshot
contents remain identical to the initial candidate. Final-head hosted results are recorded in the
PR and delivery report, without misreporting this initial failed run as passed.
