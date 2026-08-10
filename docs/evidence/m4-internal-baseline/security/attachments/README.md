# M4 Attachment Security Evidence

Result: **Pass**

`tests/integration/test_profile_photos.py` proves that the profile-photo flow:

- accepts only detected JPEG/PNG content within byte, pixel, and decompression limits;
- rejects HTML, SVG, mismatched declarations, malformed images, oversize/decompression payloads,
  and cross-household access;
- stages separately, finalizes to immutable randomized storage keys, checksums bytes, and cleans
  orphaned staging records and untracked crash-window files;
- serializes the idempotency lookup with staging so concurrent identical uploads return one stored
  result without leaking a losing staged file or exposing a uniqueness error;
- serializes staging, finalization, and cleanup with a cross-process filesystem lock so cleanup
  cannot remove an in-progress immutable version;
- selects only finalized versions owned by the same household and animal; and
- delivers through an authenticated endpoint with a safe fixed media type, `nosniff`, private
  caching, and no server-executable storage path.

Reproduce with:

```sh
uv run pytest tests/integration/test_profile_photos.py \
  tests/browser/test_animal_care_workflow.py::test_authenticated_keeper_can_upload_and_view_an_immutable_profile_photo -q
```

Result: 3 tests passed after qualification against Pillow 12.3.0. Attachment manifests used by the
backup pipeline are derived from the completed SQLite copy, not the changing live database.

The final review test proves dimension and pixel limits are enforced before Pillow decodes image
data. The final Trivy scan reported zero fixed high or critical findings.

The corrected real-browser run also selected a finalized PNG through the authenticated profile
flow, rendered its descriptive alternative text on the profile, displayed that selected version on
the animal listing, and included exactly one attachment in the verified backup/restore rehearsal.
