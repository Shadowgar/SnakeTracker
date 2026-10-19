# Natural History: local content and explicit publication

Natural History explains a species in the wild. Reviewed Captive Care remains a separate,
immutable authority for feeding, conditions and enclosures. Neither descriptions nor structured
wild facts create schedules, reminders, feeding rules or animal-record changes.

## Offline content workflow

Migration `0025_natural_history` is additive after X2. This PR does not run it on production.
No content is bundled into startup or acquired by ordinary profile/reference/image reads.
Taxonomy controls selected names/classification; Natural History source associations attach to
permanent taxon UUIDs. Generation identifiers are optional acquisition notes without foreign keys.
Rollback or deletion of a taxonomy snapshot cannot remove retained content or its publication.

A bounded JSON document validates against `NaturalHistoryVersion` in
`src/snaketracker/application/natural_history.py`. Include the permanent UUID, matching qualified
provider identity, verified scientific name, actual originating source, revision-specific URL,
retrieval date, attribution, license/link, modification notice and source-specific rights evidence.
Descriptions are plain text, never HTML or structured-fact extraction. Structured biological
claims require their own qualification and explicit wild/life-stage/geography/sex/qualifier context.
No IUCN or third-party iNaturalist prose is qualified merely by an accessible URL.

```sh
# Validate only; no database is opened or modified.
uv run python -m snaketracker.operations.natural_history retain /absolute/qualified-version.json

# Retain without publication, only on an explicitly authorized migrated database.
uv run python -m snaketracker.operations.natural_history --database /absolute/isolated.sqlite3 --apply retain /absolute/qualified-version.json

# Review exact content, identity and source rights before selecting its returned hash/version.
uv run python -m snaketracker.operations.natural_history --database /absolute/isolated.sqlite3 --apply select ASSOCIATION 1 --sha256 CONTENT_HASH --expected-revision 0 --actor REVIEWER --reason QUALIFICATION_RECORD

# Inspect retained versions and immutable publication/withdrawal decisions.
uv run python -m snaketracker.operations.natural_history --database /absolute/isolated.sqlite3 history TAXON_UUID

# Withdraw visibility while preserving all versions and reasons.
uv run python -m snaketracker.operations.natural_history --database /absolute/isolated.sqlite3 --apply withdraw ASSOCIATION --expected-revision 1 --actor REVIEWER --reason WITHDRAWAL_RECORD
```

Selection serializes writers and rejects a stale expected revision or mismatched content hash.
A retained source revision cannot be rewritten. A new revision is retained separately and does
not replace the current published version until selected. Older retained versions can be selected
again with a new decision. Decisions and versions cannot be updated/deleted. Withdrawal does not
revoke previously received source licenses; it removes the app's selection. Retained history is an
operator view, not a public route that bypasses withdrawal.

`rights_scope=development` requires explicit `--development` selection and is visible only in
`Environment.TEST`. Production reads exclude development content. Production selection additionally
requires a source-specific `rights_scope=production` record and its evidence. These are trusted
operator attestations, not automated legal qualification. Never relabel a development fixture as a
production source-rights review. The exact-content SHA and review reason bind each selection.

## Legacy guides and recovery

Guide biology bindings classify only exact immutable guide versions/claims, verified against the
retained guide hash, original source, species scope, wild context and qualifiers. Unknown/captive
claims stay in their original guide. Equivalent qualified biological positions display together,
with one count per actual origin; distinct context or conflicting values remain separate. The
original full Care Guide version, claim and provenance remain accessible and unchanged.

Back up the complete database and mandatory keeper attachments under the existing backup contract.
Reference imagery uses existing local metadata and licensed bundled fallback; absent bytes never
trigger downloads during viewing. Startup validates source/version/publication integrity before
normal mutable initialization. A downgrade is blocked once retained X3 data exists: use forward
recovery or a separately approved historical restore, never delete retained content to downgrade.

## Development Boa example and publication limit

`reference/natural-history/boa-imperator-development.json` is a development-only adaptation from
[Wikipedia revision 1380867968](https://en.wikipedia.org/w/index.php?title=Boa_imperator&oldid=1380867968),
credited to Wikipedia contributors under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/),
with the changes stated in the document and view. The source identity was independently checked
against [iNaturalist taxon 539399](https://www.inaturalist.org/taxa/539399).
[Wikipedia's reuse policy](https://en.wikipedia.org/wiki/Wikipedia:Copyrights#Reusers'_rights_and_obligations)
requires attribution, licensing and modification notices; imagery has separate rights.

This fixture does not assert production publication approval. Production rights qualification,
any production migration/import and deployment need separate authorization. Conservation and
other unsupported structured facts remain unavailable. Existing photo credits/licenses remain
unchanged; a text license never qualifies an image.
