# Care Keeper Updates page — deployment recording

This page is intentionally split into **historical development milestones** and **confirmed
production updates**. The bundled feature history is audited from 294 commits and 23 PRs in
`docs/evidence/updates/`. Its dates are merge dates, *not* confirmed production install dates.

## What users see

- `/updates`, accessible to signed-in users from More.
- Photo-led feature highlights, the complete older history grouped by month, and one optional
  chart of 21 *merged pull requests* across August–October 2026. It does not use household data.
- The **On this website** section reads only an optional, operator-maintained JSON ledger.
  A missing ledger means earlier deployment dates have not been verified; it does **not** mean
  there have been zero earlier deployments.
- Existing local animal-group illustrations are used without remote image requests.

## Recording actual production updates (not part of this PR's deployment)

The ledger path is `<database directory>/production-release-history.json`. The application
only **reads** this file, never creates or rewrites it. It must remain on the same persistent
host volume through image upgrades and rollbacks and be included with operational recovery
materials. No new application database tables or migrations are needed.

The operator must prepare user-friendly release notes *before* deployment but write the
ledger **only after** separately authorized deployment verification. Confirm the running
build, readiness, user-critical workflows, actual deployment timestamp, and recovery
point. If verification fails, do not publish a success record.

Each ledger entry must use this schema:

```json
{
  "verified": true,
  "version": "1.0.0",
  "status": "deployed",
  "deployed_at": "2026-10-18T20:00:00-04:00",
  "build_sha": "0123456789012345678901234567890123456789",
  "title": "What's new for your animals",
  "description": "A shorter, friendly explanation of what changed.",
  "changes": [
    {"kind": "New", "text": "Look up more species by name."},
    {"kind": "Improved", "text": "Find your saved care notes more easily."},
    {"kind": "Fixed", "text": "Fixed a problem with ..."}
  ]
}
```

Use **real** dates and the actual running build SHA, not the example values above.
`status` is `deployed` for a verified upgrade and `rolled_back` for a verified
reversion. Do not remove historical entries when rolling back. No unverified, failed,
staged or PR-only release may carry `verified:true`.

Append to the existing JSON array by creating a new 0600 temporary file **in the same
persistent directory**, validate the entire JSON and the new record, then atomically
replace the ledger and fsync the parent directory. Keep the old ledger as part of the
verified recovery set before replacing it. Do not use a non-atomic in-place edit,
overwriting a previous version, or temporary storage outside the persistent volume.
Only the trusted release operator should be able to update this file; the web app should
have read access only. Never put secrets, real household data, private incident details,
or internal storage locations in notes.

If publication fails, the deployment must still be safely recoverable; reconcile the
ledger afterward using the independently verified deployment receipt. Do not invent
historical entries when no such receipt exists.

## Editorial principles

**What is new? What got easier? What was fixed? Do I need to do anything?**

Describe changes for someone caring for animals, not for a developer. Feature photos can
be reused from the local generic animal fallback set; do not mislabel them as a user's
own animal or a scientifically verified species photo. Graphs must use measured, dated,
sourced figures and must never fabricate usage, animal counts, or adoption statistics.

Every future production update needs one human-readable, verified entry. Its date must
reflect the successful deployment, not PR merge. The page itself adds no production
change during code review and does not backfill prior deployments automatically.
