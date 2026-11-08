# Release history and evidence reconciliation

The current deployed release is the **November 8 retry**. All counts and health/
capacity observations below are dated receipts, not a fresh production probe by
this documentation task. No previous receipt or branch is rewritten.

| Event, America/New_York | Outcome and exact source | Preservation / evidence |
| --- | --- | --- |
| November 4, 10:50 EST activation; November 6, 23:46 EST final verification/entry | Original combined release deployed: source `8ebffb6287742f3aef5ad985ef99cf1036a3c623`; merge `71eb88c01390d3672c470c1a50a80e707233c181` has the identical qualified tree | Schema 25 → 26 → 27; 109 pre-existing tables preserved, 35 final protected-table comparisons, 1,051 events and 46 attachment versions preserved. Recovery `53785bb3-bace-478e-9891-eb4aa052af86` is the pre-upgrade schema 25 point. The initial 502 and later successful smoke remain recorded. |
| November 7, 05:15:48 EST recovery | PR #34/#35 attempt rolled back to `8ebffb6`; **ROLLED BACK — PRODUCTION HEALTHY** | An operator guard mistook unset DNS `[]`/`null` representations for drift. Candidate public traffic never reopened. 158.439 seconds interruption; schema 27, 1,052 events, 46 attachments preserved; no database restore. New schema 27 recovery `5a52775c-17be-4730-a6a0-b5a51de743a3`. [Original dated rollback document](../roadmap-continuation-20261107/production-rollback-20261107.md) copied byte-for-byte. |
| November 8, 00:36:18 EST traffic reopened; 00:46:24 EST acceptance recorded | **DEPLOYED AND VERIFIED**, source `cf772cf8348f3eeb2ec069754b585bffd6c926cf` | One authorized retry; 28.27 seconds interruption; schema 27, 1,053 events, 46 attachments and 12 backups preserved. Fresh recovery `741e4100-8f62-4146-9f2d-d596f9c3bc79`; 109 final table comparisons with exact operational-session accounting; no rollback or migration. [Detailed retry record](../roadmap-continuation-20261107/production-retry-20261108.md). |

Current image:
`sha256:1f9ea52a9ce535f50a2d5e4795d5f62b13c0dc4f297ac58191d6bbf1611cdc39`.
Artifact 13565316198 in [qualification run 42350262143](https://github.com/Shadowgar/SnakeTracker/actions/runs/42350262143).
The final November 8 closeout measured 7,539,240,960 bytes (~7.02 GiB) free at
05:49:55 UTC, above the 6,710,886,400-byte remaining-operation reserve. These figures
are not promises about current free space or later legitimate user records.

The November 8 browser receipt records 21 page checks (including repeated viewports),
eight readiness/static checks, proportional Plant photos at 1440/390/320 px,
Watering/History access, attribution, zero horizontal overflow and zero automated
axe violations. Four harness assumptions were corrected and retained as diagnostics;
the unchanged application image passed the corrected checks. No new iPhone or
VoiceOver acceptance is implied.

The historical November 7 document's “not live” and “new owner decision required”
statements describe its then-current outcome. November 8's later explicit retry
authorization and verified deployment supersede that status, not the original
incident record. Similarly, the November 4–6 receipt's open dependency alerts are
historical; the November 8 GitHub refresh recorded zero open alerts after the
qualified PR #34/#35 prerequisite updates. The missing full-archive qualification and
unpublished Frog/Natural History content were not resolved by deployment.

## How the unmerged documentation is reconciled

- `f6f0069a556f1720ceea1ef7c722be05cf6d6830` remains the unmerged November 7 branch.
  Its dated incident file is retained unchanged here; its then-current status is
  not applied over the later successful release.
- `413b4cd5217e135067c8fcca9b37b0d9c8d9d039` remains the unmerged November 8 branch.
  This PR incorporates its documentation changes and adds the final acceptance
  audit, rather than merging either branch automatically.
- This PR starts from current main `cf772cf` and changes documentation only.
  The frozen roadmap, architecture approvals, application/configuration, deployed
  image and original output evidence remain untouched. Current status is supplied
  by the [acceptance package](README.md) and roadmap supplement.

[Release evidence extract](release-evidence.json) contains only selected dated
facts plus SHA256 hashes and workspace paths of the original machine receipts.
Full operator evidence remains in `output/combined-production-deploy-20261104/`,
`output/combined-production-deploy-20261107/`, and
`output/combined-production-retry-20261108/`. The extract is a traceable summary,
not a new deployment/backup/health qualification or an owner acceptance record.
