# Offline release inventory and signature evidence

The operator CLI converts an already retained Trivy v2 **container-image package
inventory** into a [CycloneDX 1.6 JSON SBOM](https://cyclonedx.org/docs/1.6/json/).
It also creates an index binding the exact SBOM, scan bytes, deployable archive,
image configuration digest and source revision. A separate command verifies that
index's detached Ed25519 signature against a public key explicitly supplied by the
operator. No image is built, loaded or scanned; no database or service is opened.

This supplements the [release compatibility exporter](../evidence/roadmap-continuation-20261107/README.md#implemented-release-readiness-improvement);
inventory, compatibility declarations, signatures and actual
release qualification are distinct evidence. M7/M8 remain open until their
required operational evidence and owner decisions exist.

## Export retained evidence

Use the accepted qualification receipt to select the exact image, source and
archive digest. Derive the scan digest from the scan bytes inside the already
checksum-verified qualification artifact, not from an untrusted replacement file.
The CLI requires all four pins and refuses missing/ambiguous package inventories,
identity mismatches, duplicate JSON keys and an existing output directory.

```sh
python -B -m snaketracker.operations.release_evidence export \
  --scan /retained/arm64-scan.json \
  --scan-sha256 "$QUALIFIED_SCAN_SHA256" \
  --archive /retained/image.tar.gz \
  --archive-sha256 "$QUALIFIED_ARCHIVE_SHA256" \
  --image-id "$QUALIFIED_IMAGE_ID" \
  --source-sha "$QUALIFIED_SOURCE_SHA" \
  --output /new/release-evidence
```

The two output files are `sbom.cdx.json` and `release-evidence.json`. Existing
inputs are read without mutation; the large archive is hashed in 1 MiB chunks.
JSON reads are limited to 64 MiB. If writing fails, retain any partial output for
diagnosis and choose a new output directory; the tool never overwrites it.

Components preserve observed names, versions, package URLs, license declarations
and per-target occurrences, including libraries embedded separately in `uv` and
`uvx`. The converter does not infer a complete dependency graph or a license
grant. SBOM composition completeness is explicitly `unknown`. The image hash is
the **Docker image configuration digest**, not an invented registry manifest digest.

The exported index reports `signature: not_supplied` and
`qualification: not_asserted`. This unsigned preparation is not a signature gate
pass. A checksum establishes byte identity only relative to its trusted receipt.

## Verify an externally signed index

The signing authority, private-key custody, independent recovery and trusted
public-key distribution need an explicit operational decision. This tool creates
no key, obtains no signing credentials and chooses no trust root. Do not reuse
application runtime secrets or backup-encryption keys for release signing.

Once a separately authorized signer has signed the **exact bytes** of
`release-evidence.json` with Ed25519, retain that detached 64-byte signature. The
index binds the artifact bytes through their SHA-256 digest; the artifact is not
copied or rewritten. Retain the original index unchanged, including its export-time
unsigned status. Verify using the independently trusted PEM public key:

```sh
python -B -m snaketracker.operations.release_evidence verify \
  --bundle /retained/release-evidence \
  --scan /retained/arm64-scan.json \
  --archive /retained/image.tar.gz \
  --signature /retained/release-evidence.ed25519 \
  --public-key /trusted/release-signing-public.pem
```

Verification requires a valid signature, every signed file digest/size, exact
source/image identities and the deterministic SBOM conversion. A key bundled by
an untrusted artifact is not an independently trusted key. The result names the
trusted raw-public-key SHA-256 fingerprint and reports `verified_ed25519`;
qualification remains `not_asserted`. Verification proves the supplied key signed
these exact bytes; signer authority and release approval remain separate.

Production release signing remains outstanding until that trust/custody decision
and an actual authorized signature exist. Test-generated keys demonstrate only
the verifier's behavior.

## Retained qualification

The [November 8 offline conversion receipt](../evidence/m78-release-evidence-20261108/README.md)
reuses the deployed ARM64 inventory and accepted archive without a new scan or
build. It records the resulting standard SBOM and the remaining public-release
gates; it does not enable public sharing or complete M7/M8.
