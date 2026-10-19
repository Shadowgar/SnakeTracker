# X3 — Natural History development qualification

Owner-authorized development from `94ea887f4302e58eae18985c34f3f910da2df2c9`.
No production migration, import, publication or deployment; no X4 implementation.
ADR statuses, protected plans and existing approval hashes remain unchanged.

## What people can do

Learn about a linked species' identity, natural range and life in the wild, independently
of whether a reviewed captive-care guide exists. Read the locally saved description and
source revision when providers are offline. Open source/version details or the full
immutable Care Guide. Missing or withdrawn information remains explicit; wild facts do
not change the animal's care settings, records or schedules.

## Acceptance map

| Requirement | Executed qualification |
| --- | --- |
| AT-NATHIST-01 identity, retention and publication | Integration lifecycle tests: matching permanent UUID/provider/name, immutable revisions, idempotent retention, exact hash and rights scope, stale selection races, explicit withdrawal and retained audit |
| AT-NATHIST-01 guide coexistence | Contextual/origin tests: equivalent positions, one origin via two intermediaries, distinct geography, disagreements, exact immutable-guide bindings, missing/unknown/captive context, original life stage and absent qualifiers |
| AT-NATHIST-01 Boa imperator / 539399 | Development fixture checked against iNaturalist identity and direct Wikipedia revision; linked Boa without a reviewed guide renders useful local description and exact missing-guide wording |
| AT-PROFILE-REF-01 local viewing/privacy | Transport rejection during Animal/Reference/Directory/image reads; every persisted table compared except explicitly permitted sessions/security audit; warm and withdrawn/cold states; unauthenticated Animal reference denied |
| AT-PRODCOMP-01 applicable X3 cases | Scratch backup/restore and additive 0024→0025 upgrade preserve all prior table contents and guide payloads; actual previous-main compatibility reader refuses 0025; retained-data downgrade blocked; B→A taxonomy rollback and cleanup preserve content |
| Visual/accessibility | Actual Chromium desktop 1440×900, mobile 390×844 and 320×844; no overflow, local photo loaded, strict local requests, Enter/Space sources disclosure, reduced motion; existing bottom navigation retained |

Screenshots: [390px](screenshots/boa-390.png), [320px](screenshots/boa-320.png),
[desktop](screenshots/boa-1440.png), [full mobile](screenshots/boa-390-full.png),
[full desktop](screenshots/boa-1440-full.png).
All screenshots use a fictional keeper and Animal in a separate `/tmp` database.
The amber development notice is intentional; production excludes development-only versions.

## Rights and operational limits

The prose fixture is a shortened adaptation under CC BY-SA 4.0, with originating Wikipedia
revision, authors, license and changes retained. No structured claims are inferred from prose.
No direct IUCN content or iNaturalist-mediated third-party text is republished as an independent
source. Existing licensed photo provenance is retained. See the
[operator/source policy](../../../operations/natural-history.md) for separate production rights
qualification. The fixture is not production-approved and is never imported at startup.

No production-sized X2 taxonomy import/backup rehearsal was performed in X3. Existing broader
compatibility, replay, photo-priority and guide tests remain required by the ordinary hosted
Quality gate. Passing local synthetic qualification is not production deployment acceptance.

Fresh review found and corrected missing publication-pointer detection, legacy life-stage
preservation and absent-qualifier representation; regression tests now cover all three.
Final exact-head hosted results are reported in the PR and delivery report.

Local results: 16 focused X3 checks passed, then both guide-view integration checks passed
(including the newly added immutable-guide display case). Ruff, formatting, mypy, architecture,
freeze, documentation links and diff checks passed. Existing test-client deprecation warnings
remain reported. No local full quality gate was launched; ordinary hosted Quality is authoritative
for the final PR tree. See the implementation record for the earlier wider-run schema assertion.
