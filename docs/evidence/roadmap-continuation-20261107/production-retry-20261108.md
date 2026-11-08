# November 8 combined production retry — deployed and verified

**DEPLOYED AND VERIFIED.** The owner-authorized single retry activated the exact
qualified PR #34/#35 release on November 8, 2026 at **05:36:18.209375 UTC /
00:36:18.209375 EST**. Proxy maintenance lasted **28.27 seconds**. Final production
acceptance was recorded at **05:46:24.973513 UTC / 00:46:24.973513 EST**.

| Identity | Verified value |
| --- | --- |
| Current production source | `cf772cf8348f3eeb2ec069754b585bffd6c926cf` |
| Current ARM64 image | `sha256:1f9ea52a9ce535f50a2d5e4795d5f62b13c0dc4f297ac58191d6bbf1611cdc39` |
| Qualified artifact | `13565316198`, [run 42350262143](https://github.com/Shadowgar/SnakeTracker/actions/runs/42350262143) |
| Previous source | `8ebffb6287742f3aef5ad985ef99cf1036a3c623` |
| Retained known-good image | `sha256:ab0ddd40f4d54db63b6945146e163a0431670a62e8a112c5b06a675c1c5818f4` |
| Fresh recovery point | `741e4100-8f62-4146-9f2d-d596f9c3bc79` |
| Schema | `0027_bioactive_plant_care` (27), unchanged |

## Qualification, recovery and preservation

GitHub main remained at the authorized target; Quality, Container and ARM64 release
qualification remained successful. The accepted 1,719-test qualification and actual
ARM64 scan were reused. Artifact checksums, image/source identity and the installed
compatibility manifest matched. No image rebuild, security scan, migration or full
application-suite rerun was performed for the retry.

Legitimate production activity advanced the event high-water to **1,053**, so the
supported worker produced the fresh encrypted recovery point above. Isolated
restoration passed. The prior November 7 recovery point
`5a52775c-17be-4730-a6a0-b5a51de743a3` remains retained.

Final comparison inventoried **110 tables** and compared **109**, excluding only
the transient backup lease table and normalizing only
`reminder_facts.calculated_at`. The exact temporary operator session and its two
audit rows were accounted for; the session was revoked after browser validation.
There were **no unexpected table differences**. All **1,053 event records**,
**46 attachment versions / 8,836,039 bytes**, and **12 retained backup archives**
were preserved. Accounts, memberships, Animals, plants, enclosures, schedules,
reminders and care history remain intact. SQLite integrity was **ok** with **zero
foreign-key errors**. No artificial production care event was generated.

Web, worker and nginx were healthy with **zero automatic restarts**. Background
processing retained 44 succeeded jobs and zero projection backlog. Runtime
configuration, secrets and persistent mounts were preserved. Free filesystem space
was **7,668,527,104 bytes (7.142 GiB)** before cutover and
**7,540,764,672 bytes (7.023 GiB)** at final verification, above the
**6,710,886,400-byte** remaining-operation reserve.

## Actual deployed browser acceptance

The authenticated GET-only browser checks passed **21 routes** and **eight
static/readiness checks**. They covered HTTPS/authentication, PWA assets, Plant
Detail, Animal and Directory screens, Smart Care, Bioactive, photographs and
attribution. Watering and History remained accessible; no business form was
submitted.

| Plant viewport | Photo border box | Painted portrait bitmap |
| --- | --- | --- |
| 1440 px | 176 × 224 px | 124.875 × 222 px |
| 390 px | 112 × 197.547 px | 109.995 × 195.547 px |
| 320 px | 112 × 197.547 px | 109.995 × 195.547 px |

The contained bitmap retains its actual proportions; the bounded border box does
not reproduce the prior 800 px-tall thumbnail defect. All three widths passed
layout checks with **zero horizontal overflow** and **zero axe violations**.
**The Plant Detail layout fix is live.** Physical-device and screen-reader owner
acceptance remain separate from these Chromium checks.

The retained smoke record also preserves four harness diagnoses: selecting the
actual reference image on the demo profile, distinguishing a contained portrait
bitmap from its border box, evaluating accessibility without violating the page's
CSP, and recognizing the Directory's empty-query landing state. Corrected checks
passed against the unchanged deployed image. These were verification-harness
assumptions, not established application failures or a reason to rebuild the image.

## Earlier attempt and rollback readiness

The November 7 attempt restored the old source after 2 minutes 38 seconds of
maintenance. Its operator guard incorrectly distinguished unset Docker DNS-list
representations. That failed attempt and its successful recovery remain preserved
in `output/combined-production-deploy-20261107/`. The unmerged rollback documentation
commit `f6f0069a556f1720ceea1ef7c722be05cf6d6830` was not merged or used as this
branch's parent; this documentation starts from exact target main.

The retry executed the corrected guard, which normalizes only equivalent unset
DNS-list representations and continues to reject real protected configuration
changes. **No rollback was performed during this retry.** The compatible old
binary, pinned Compose selection, fresh recovery point and all previous recovery
assets remain available. The production database was never replaced or restored.

## Scope and retained evidence

Frog Guides and development Natural History remain unpublished; unpublished-content
and public-sharing tables are unchanged. No public profiles, galleries or M9
functionality were enabled. M9 implementation has not started. Deployment does not
constitute formal M6.6 acceptance or complete M7/M8 qualification.

The annotated Swiss Cheese Plant asset retains its existing provenance. Its foreign-
language captions and magenta annotations remain a separate content-suitability
issue; replacement still requires qualified acquisition and separate publication
authorization. Same-device recovery and outstanding off-device/key/storage/manual
acceptance requirements remain explicit in [M6.6 closeout](m66-closeout.md) and the
[current roadmap supplement](README.md).

Operator evidence is in `output/combined-production-retry-20261108/` in the shared
workspace: `FINAL-VERIFICATION.json`, `FINAL-DATA-VERIFICATION.json`,
`cutover-receipt.json`, `isolated-restore-result.json`, `live-browser-smoke.json`,
`github-release-refresh.json`, `security-alert-refresh.json` and the final report.
The first attempt's receipts remain unchanged. This documentation is kept on a
separate branch for normal review; it does not modify the qualified release source
or merge the prior rollback documentation branch.
