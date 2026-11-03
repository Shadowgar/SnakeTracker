# X5 — species-specific Amphibian Care Guides

Status: implemented for owner design/source review; **not merged or deployed**.
Base: `ad64e91f0bc696308baa21a6f6e1607e442d8d72` (PR #28 included).
Scope: [owner-directive implementation plan](plan.md).

The [new version-1 bundle](../../../../reference/care-guides/reviewed-amphibians-v1.json)
contains **two guides, five source pages from three publishers, and 42 claims**:
White's tree frog (**Pelodryas caerulea**, source synonym Litoria caerulea) and
Cranwell's horned frog (**Ceratophrys cranwelli**). [Research and source-to-claim map](sources.md)
records exact identities, originating sources, retrieval limits, rights and scope.
Existing reviewed bundles remain byte-identical. [What's New](whats-new-draft.md) is an
unpublished draft, not a release entry.

## Implementation

- Extend the existing global `GuideGroup` and selectors; no second guidance system.
- Revision `0026_amphibian_care_guides` rebuilds only `care_guide_versions` inside the
  established transactional migration envelope, copying stored values without
  reserializing JSON and restoring original trigger SQL. All existing groups remain.
- New Amphibian imports require an exact selected, accepted species with qualified
  provider mappings and Amphibia classification/ancestry. Synonym/common-name/genus
  inference is not used. Duplicate exact taxa and unqualified taxa fail atomically.
- The existing local reference page now shows measurement context, review date and
  visible precautions. Independent source positions and life stages stay separate;
  native keyboard-accessible disclosures retain deeper provenance. Natural History
  and keeper records remain independent. No new care commands or schedules exist.
- New startup schema recognition preserves fail-closed older-binary behavior. The
  Natural History operator accepts both its previous schema and the new schema.

## Qualification

The original qualification and screenshots in this section belong to revision
`382d9ccce245a5692b7907a0cbac06000a8f19be`. They are retained unchanged. Fresh evidence
for the bounded mobile follow-up is recorded under [Mobile completion](#mobile-completion).

| Acceptance evidence | Result |
| --- | --- |
| `AT-AMPHREF-01`: bundle validation, selectors, idempotent imports, changed-version rejection, exact/missing/ambiguous/genus/inactive/wrong-class rejection | Passed in focused X5 suite |
| Every non-guide table unchanged during populated import | Passed using X4's real fictional command/projection fixture |
| Existing guide rows, IDs, hashes, current pointers, source/claim records and six triggers survive upgrade/downgrade/re-upgrade | Passed on actual SQLite **3.40.1**, `trusted_schema=OFF`, FK enforcement restored |
| No JSON expression indexes; integrity and foreign-key checks; two new guides import idempotently on 3.40.1 | Passed; [runtime evidence](sqlite340.log) |
| Downgrade with Amphibian versions present | Rejected before mutation; stored tables unchanged |
| Actual previous release `ad64e91` web and worker startup against X5 database | Both reject before mutable startup; DB bytes and table hashes unchanged |
| Encrypted normal-worker backup and isolated recovery | Passed; guide/reference and household tables retained, attachment bytes retained; only expected backup-job bookkeeping differs from capture |
| Ordinary reference GETs offline and mutation-free | Socket connect forbidden; all tables unchanged except permitted auth/session bookkeeping |
| Natural History without a reviewed guide; manual/unlinked Animal | Passed; independent text remains available and no unsupported guide attaches |
| Adult feeding and UVB disagreements; juvenile feeding and habitat corroboration | Preserved and tested, with source-specific qualifiers |
| Browser at 390×844, 320×844, 1440×900 | See [browser results](browser-results.json) and screenshots below |
| Broader unchanged quality/hosted gates | Final outcomes and exact commit are recorded in the PR; no threshold changes or suppressions |

Focused command: `TMPDIR=/dev/shm/carekeeper-x5-quality uv run pytest -q tests/integration/test_x5*.py`.
Final focused result: **15 passed**. The suite reuses X4's populated historical v1/v2/v3
profiles/events, linked taxa, source versions, measurements and attachment fixture.
The broader unchanged gate covers existing X1–X4 behavior; no production-sized archive,
backup-infrastructure investigation or unrelated long-running workload was restarted.

The first local full-gate attempt encountered SD-card fsync timeouts and was stopped.
The same gate was rerun with test databases in memory-backed scratch space, without
changing test timeouts or thresholds. Hosted checks remain the unchanged authoritative
gates. This environmental attempt is not counted as a pass.

Reproduce the runtime probe with a separately built disposable image providing SQLite
3.40.1 and this checkout mounted read-only at `/qualification`:

```sh
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m --cap-drop ALL \
  --security-opt no-new-privileges \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/qualification/src \
  -v "$PWD:/qualification:ro" --entrypoint python \
  snaketracker:sqlite340-380db246f090 /qualification/scripts/qualification/x5_sqlite_runtime.py
```

No production volume, credentials or service is used. The image is the already available
PR #28 qualification image; X5 source/migrations are supplied by the read-only checkout.

## Browser and owner design review

All Animals/accounts are fictional. Photographs are **species reference images**, not
claimed photographs of those fictional Animals. The CC-BY photo identities, authors,
licenses and observation URLs are recorded in [media provenance](browser-media.json).
They were explicitly acquired during fixture preparation, normalized by the existing
local cache, then served locally. Screenshots reproduce those photographs with visible
attribution; no source image is redistributed as a separate repository asset.

No new Natural History publication is part of X5. Screenshots show its independent
unavailable state; the test suite separately proves retained Natural History remains
visible without a reviewed guide. The fixture's taxonomy provider is deliberately
labelled Fixture; actual scientific mapping was verified separately in the research.

| Species | 390×844 | 320×844 | 1440×900 |
| --- | --- | --- | --- |
| White's tree frog | [Full](screenshots/pelodryas-390x844-full-page.png) · [Summary](screenshots/pelodryas-390x844-care-summary.png) · [Expanded sources](screenshots/pelodryas-390x844-expanded-sources.png) | [Full](screenshots/pelodryas-320x844-full-page.png) · [Summary](screenshots/pelodryas-320x844-care-summary.png) · [Expanded sources](screenshots/pelodryas-320x844-expanded-sources.png) | [Full](screenshots/pelodryas-1440x900-full-page.png) · [Summary](screenshots/pelodryas-1440x900-care-summary.png) · [Expanded sources](screenshots/pelodryas-1440x900-expanded-sources.png) |
| Cranwell's horned frog | [Full](screenshots/ceratophrys-390x844-full-page.png) · [Summary](screenshots/ceratophrys-390x844-care-summary.png) · [Expanded sources](screenshots/ceratophrys-390x844-expanded-sources.png) | [Full](screenshots/ceratophrys-320x844-full-page.png) · [Summary](screenshots/ceratophrys-320x844-care-summary.png) · [Expanded sources](screenshots/ceratophrys-320x844-expanded-sources.png) | [Full](screenshots/ceratophrys-1440x900-full-page.png) · [Summary](screenshots/ceratophrys-1440x900-care-summary.png) · [Expanded sources](screenshots/ceratophrys-1440x900-expanded-sources.png) |
| No reviewed guide | [390](screenshots/rana-390x844-full-page.png) | [320](screenshots/rana-320x844-full-page.png) | [1440](screenshots/rana-1440x900-full-page.png) |

Run `PYTHONPATH=. uv run python scripts/qualification/x5_browser_fixture.py --data-dir
/tmp/carekeeper-x5-browser-NEW --port 8107` for a new isolated fixture. Optional
`--media-dir` accepts the separately acquired, reviewed photographs named in the media
manifest; ordinary serving blocks socket connections. Run the browser script with
`X5_FIXTURE`, `X5_PLAYWRIGHT` and `X5_AXE` pointing to the fixture and local tools.
The browser script uses same-origin axe injection under the application's normal CSP,
checks WCAG A/AA including text contrast, horizontal overflow, native disclosure
Enter/Space behavior, Overview/reference navigation and external request counts.

## Mobile completion

The 2026-11-03 follow-up places Reviewed Captive Care before the empty Natural History
section at widths up to 800px, only for linked Amphibians with a reviewed guide and no
Natural History content. The identity/photo, visible care precautions, separate Natural
History unavailable state, sources and review dates remain. Desktop section order and
the no-guide experience are unchanged. The applicability introduction explains
post-metamorphic as care for frogs after the tadpole stage; source claims are unchanged.

Fresh focused validation:

- `TMPDIR=/dev/shm/carekeeper-x5-mobile-tests uv run pytest -q tests/integration/test_x5_amphibian_guides.py tests/integration/test_natural_history_web.py tests/integration/test_care_guides.py`
  — **21 passed**; one pre-existing Starlette TestClient deprecation warning. Coverage
  includes Amphibians with retained Natural History, no-guide and unlinked Animals,
  visible cautions, source dates, offline rendering and unchanged non-session data.
- The new rendering test and browser position assertion each failed on the original
  presentation, then passed after the bounded template/CSS change.
- `uv run ruff check tests/integration/test_x5_amphibian_guides.py`,
  `uv run ruff format --check tests/integration/test_x5_amphibian_guides.py`,
  `node --check scripts/qualification/x5_browser_review.js`, and `git diff --check`
  passed.
- Documentation links passed across 265 files; the architecture freeze check passed
  for HEAD, index and working tree.
- [Fresh browser results](mobile-completion/browser-results.json): all nine
  species/viewport combinations passed at 320×844, 390×844 and 1440×900. Checks cover
  section positions, loaded photographs, precautions outside disclosures, source/review
  dates, keyboard disclosure behavior, navigation, no horizontal overflow, and zero
  automated WCAG A/AA violations, external requests or page errors. These are Chromium
  checks, not a manual screen-reader or physical-device certification. CSS changes
  visual section order on mobile; the existing document/keyboard section order remains.

Six representative captures were added; the original captures above were not replaced:

| Case | Current captures |
| --- | --- |
| White's tree frog, 390×844 | [Initial view](mobile-completion/pelodryas-390x844-initial-view.png) · [Full page](mobile-completion/pelodryas-390x844-full-page.png) |
| Cranwell's horned frog, 320×844 | [Initial view](mobile-completion/ceratophrys-320x844-initial-view.png) |
| No reviewed guide, 390×844 | [Initial view](mobile-completion/rana-390x844-initial-view.png) |
| White's tree frog, 1440×900 | [Initial view](mobile-completion/pelodryas-1440x900-initial-view.png) · [Full page](mobile-completion/pelodryas-1440x900-full-page.png) |

The disposable fixture used `/tmp/carekeeper-x5-browser-mobile-completion`, port 8115
and the already reviewed photos in `/tmp/carekeeper-x5-research`. Run the existing
browser script with `X5_CAPTURE_SET=mobile-completion` to save only this representative
capture set while retaining all nine viewport/species checks. All testing used
fictional data. Source research, reviewed bundles, migration, immutable history and
production were unchanged; their unaffected original evidence is reused, not claimed
as newly rerun.

## Review and publication boundary

An independent read-only review identified omitted NSW source positions and hidden
heat-control precautions. Both were corrected with failing-then-passing regression
tests. No further static import/migration defect was reported. Hosted Codex review
outcomes are tracked in the PR alongside Quality, Container and GitGuardian.

Source availability can change; the local reviewed snapshot stays stable. Source review
and design acceptance remain the owner's decision. Corrections after import require a
new version. Do not deploy, migrate/import into production, merge, or record a release
without owner authorization. Production data, records, media, backups, accounts and
containers were not touched by this work.
