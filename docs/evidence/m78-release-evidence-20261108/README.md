# M7/M8 release evidence automation — November 8, 2026

**M7/M8 remain open. Public enablement is not authorized by this evidence.**
Independent M9 implementation may proceed under the owner's November 8 direction;
the earlier private-album handoff does not replace the frozen public-sharing scope.

## Implemented improvement

The [offline operator tool](../../../src/snaketracker/operations/release_evidence.py)
converts retained package inventories into CycloneDX 1.6 JSON, binds the output to
an exact image/source/archive in a deterministic index, and verifies externally
created detached Ed25519 signatures using an explicitly supplied trusted public
key. [Usage and trust boundaries](../../operations/release-evidence.md) explain
the required pins and the distinction between signatures and qualification.

No production startup/configuration, schema, event contract, dependency, backup
format or runtime service changes. No application database is opened; inputs are
read only and output must use a new directory. No signing key is generated or
selected for production.

## Actual retained-image conversion

[Conversion receipt](conversion-receipt.json) binds this local conversion to the
accepted [ARM64 qualification run 42350262143](https://github.com/Shadowgar/SnakeTracker/actions/runs/42350262143):

| Item | Exact retained identity |
| --- | --- |
| Source | `cf772cf8348f3eeb2ec069754b585bffd6c926cf` |
| ARM64 image configuration digest | `sha256:1f9ea52a9ce535f50a2d5e4795d5f62b13c0dc4f297ac58191d6bbf1611cdc39` |
| Qualification artifact | `13565176872`; ZIP SHA-256 `3013b4cea5b6187af5dee8901035f924316095e174adf58ee391c1a61280857a` |
| Retained scan SHA-256 | `0a42aae639aa6443b93be9013aeaa705ac3e974ffdeae37b4b10d4783615988c` |
| Deployable archive SHA-256 | `92ae80dc4a755f92c59be71ad6982e504e6d3cd1f2bbb485fbd728283f718f60` |
| Generated SBOM SHA-256 | `bf26580823edc8a4998dc359b29b01191b24432f8c4acb2ef522772fae1b4131` |

The existing qualification ZIP matched its accepted checksum; retained scan bytes
matched that ZIP's member. The converter rehashed the retained deployable archive
against its accepted receipt. The resulting SBOM has **1,145 package occurrences**:
97 Debian, 36 Python, 506 in `uv`, and 506 in `uvx`. Embedded-library occurrences
remain separate; dependency completeness is not inferred. The SBOM passed the
CycloneDX 1.6 JSON schema using locally available schema resources, without any
network resolution. The installed validator's error-message formatter needed a
process-local workaround for sorting dictionaries in a failed `oneOf` branch;
validation rules and the schema were not changed.

The artifacts remain in the shared workspace under
`output/m78-offline-evidence-20261108/qualified-image-sbom/`. The source scan and
archive remain at their original paths; neither image nor scan was regenerated.
The result is **unsigned**: signature-verifier tests use ephemeral fictional keys
and do not establish an authorized signature for the deployed artifact.

## Focused qualification and preservation

The focused suite covers deterministic conversion, per-target occurrences,
untrusted/malformed/ambiguous input, checksum and source/image mismatches, existing
output preservation, wrong signing keys/algorithms, unsigned verification refusal,
signed-index/scan/SBOM/archive tampering, and a signed but inconsistent SBOM. CLI
tests exercise both successful export/verification and failure exits. Source input
bytes are asserted unchanged; no application data or image execution is involved.

Existing 1,719-test, ARM64 image/security, live backup/restore and deployment
qualification retain their original scope. They were not repeated for this offline
conversion. Fresh focused test/lint/type/architecture/link results are retained
with this change; none closes the broader M7/M8 gates below.

### PR #37 review correction: exported JSON size

Review thread `PRRT_kwDOTtc1m860-2zK` identified that a small retained inventory
could expand beyond the verifier's 64 MiB JSON limit. A focused regression lowered
the limit to 4,096 bytes: a 1,854-byte inventory containing a repeated Unicode
target produced a 14,255-byte SBOM. Before the fix, the test failed with
`DID NOT RAISE ValueError`; export had created a bundle the verifier could not read.

Serialization now checks the actual UTF-8 byte length against the same bound used
by the reader. Both SBOM and index are serialized and checked before the output
directory is created. The regression verifies rejection without output or input
mutation; a boundary case verifies successful export and signature verification
at the exact size limit. The focused suite passes **30 tests with 100% line and
branch coverage**. The retained conversion and its unsigned qualification status
above are unchanged; no accepted artifact was regenerated or rescanned.

## Remaining mandatory public-release work

| Gate | Reuse already accepted | Remaining work or precise owner decision |
| --- | --- | --- |
| Off-device recovery and independent keys | November 8 encrypted recovery `741e4100-8f62-4146-9f2d-d596f9c3bc79`, isolated restore and all 46 attachment versions | Name an existing separate device/location and independent key custodian/recovery method. Recommend an owner-controlled existing computer or external medium with encrypted backup and a separately retained key; no purchase/provider selection is assumed. Prove retrieval and recovery with the Pi unavailable. |
| Native performance, thermal, storage and durability | Native ARM64/SQLite 3.40.1 operation, migration, backup and deployed preservation receipts | Qualify the representative cold/warm, CPU/memory, thermal/throttling and persistence workload. Formally reconcile the SD-only exception with ADR-0036's SSD/ext4 requirement; recommend an explicit bounded exception with measured budgets if the owner retains existing storage. This note does not waive the requirement or request hardware. |
| Supported compatibility matrix | PR #35's installed-source/schema/profile/event/projection exporter and prior actual binary/replay/migration evidence | Retain the supported fresh-install, upgrade, rollback, event/projection/plugin/backup matrix, including safe missing-plugin/newer-contract refusal. The metadata export is not that completed matrix. |
| SBOM and artifact signing | Standard SBOM now generated from accepted retained inventory; exact artifact/index verifier implemented | Select the authorized signer, independent key custody and public-key trust/distribution; retain a real signature and verification receipt. Recommendation: an independently controlled release-signing key, never a runtime or backup key. No production signature is claimed here. |
| Security, proxy, incident and recovery | Accepted exact ARM64 scan, HTTPS/PWA/worker checks, preserved live data and recovery evidence | Exercise the operator incident/recovery paths and verify the public proxy/upload/revocation behavior for the eventual M9 candidate. Complete independent M9 security review and required owner security/accessibility/performance/recovery/integrity acceptance before public enablement. |

M6.6 administrative/content decisions remain in the
[acceptance package](../m6.6-final-acceptance-20261108/README.md). They are not silently
closed or used to block unrelated implementation. M9 photo/video requirements and
its architecture/security/public-enablement gates remain governed by the frozen
[roadmap](../../roadmap/milestones.md#phase-9--m9--public-profiles-albums-and-media-sharing).
