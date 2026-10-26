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

## Codex live-link finding

The test/evidence follow-up head `e13ba92576fafe88ea5ae219d45e772836055d1b` passed the full
[Quality run 188](https://github.com/Shadowgar/SnakeTracker/actions/runs/40177541654), Container
and GitGuardian. Codex then identified a real live-link failure that the prior fixtures missed:
autocomplete leaves classification and parent fields absent, while detail supplies them. Neither
response supplies a source clock, so otherwise compatible detail created an unknown-order conflict.
The Amphibian qualification guard correctly refused to link that conflicted taxon.

The actual provider parsers now exercise search -> detail -> v2 link: red **one failed, two passed**;
green preserves classification, parent and autocomplete aliases, retains both raw observations,
and remains readable when provider transport is disabled. Name/rank contradictions still block
linking without writing a link event. A subsequent partial response cannot erase retained detail.

The narrow catalog fix combines compatible undated observations only for the same iNaturalist
identity. It requires unchanged scientific name, workflow group, rank, status, source URL and
accepted identity; conflicting known classification, parent or name values still require decisions.
Aliases remain bounded to 64 per field. No source clock is inferred from arrival time, and dated
or foreign-provider comparisons and generation/snapshot conflict rules are unchanged. Raw source
receipts remain separate from the combined selected overlay. Existing conflicts are not resolved
automatically. No ordinary read downloads or background enrichment were introduced.

Final focused result: **20 passed in 9.38s** (actual-parser integration plus ancestry/enrichment
unit checks). Existing source-order, snapshot, undated-disagreement and content-bound-decision
regressions: **nine passed in 22.08s**. Mypy and Ruff passed. New final-head hosted results and
Codex disposition are recorded in the PR and delivery report. The UI and screenshots are unchanged.
