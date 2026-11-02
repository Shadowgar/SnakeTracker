# X5 implementation and qualification

Owner directive: November 2, 2026; base `ad64e91f0bc696308baa21a6f6e1607e442d8d72`.
Proceed to an unmerged PR for design/source review. All databases, accounts and
Animals used here are disposable fixtures. No production operations are authorized.

1. Qualify two species and sources. Preserve scientific synonyms as evidence,
   source scope, life stage, units, uncertainty and actual originating publishers.
   Add a separate immutable reviewed bundle; preserve both historical bundles.
2. Test and extend `GuideGroup`, summary selectors and exact qualified imports.
   Add revision 0026 using the existing transactional FK-preserving table rebuild;
   retain all six immutable-guide triggers and historical rows. Update startup and
   operator schema compatibility without changing event/profile contracts.
3. Improve only the existing reference presentation: supported compact summary,
   measurement context, visible cautions, disclosures and existing Natural History.
4. Execute AT-AMPHREF-01 and applicable AT-PRODCOMP-01: real SQLite 3.40.1 with
   trusted_schema OFF, historical rows/constraints/triggers, populated household
   invariance, exact/missing/ambiguous identity, offline GETs, previous binary
   rejection, encrypted backup/recovery and existing X4 workflows.
5. Capture both species and no-guide fallback in actual Chromium at 390x844,
   320x844 and 1440x900; test disclosures, keyboard, contrast and overflow.
6. Run unchanged quality/hosted gates, independent branch review, and prepare the
   PR, concise evidence and an unpublished What's New draft. Do not merge/deploy.

Review focus: ambiguous or unqualified taxonomy; contextual source comparison;
SQLite reconstruction losing triggers; hidden cautions; schema-version checks
accidentally disabling Natural History tooling or older-binary preflight.

Ruling: execute the existing global-guide design from the owner's detailed directive;
no additional architecture approval loop or unrelated protected-document edits.
