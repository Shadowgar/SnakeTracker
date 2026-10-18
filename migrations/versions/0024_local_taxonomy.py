"""Permanent catalog, durable overlay and replaceable local reference generations.

Revision ID: 0024_local_taxonomy
Revises: 0023_sourced_care_guides
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0024_local_taxonomy"
down_revision = "0023_sourced_care_guides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep the exact permanent parent name and UUIDs; env.py owns atomic FK-safe rebuild.
    with op.batch_alter_table("taxa", recreate="always") as batch:
        batch.add_column(sa.Column("taxonomy_provider", sa.String(32)))
        batch.drop_constraint("ck_taxa_supported_group", type_="check")
        batch.drop_constraint("ck_taxa_status", type_="check")
        batch.create_check_constraint(
            "ck_taxa_status", "taxonomic_status IN ('accepted','synonym','inactive','unknown')"
        )
    op.execute(
        "UPDATE taxa SET taxonomy_provider=(SELECT m.provider FROM taxon_provider_mappings m "
        "WHERE m.taxon_id=taxa.taxon_id ORDER BY m.provider LIMIT 1)"
    )
    op.execute(
        "CREATE TABLE taxonomy_publications (taxon_id TEXT PRIMARY KEY REFERENCES taxa(taxon_id), "
        "source_effective_at TEXT, payload TEXT)"
    )
    op.execute("INSERT INTO taxonomy_publications SELECT taxon_id,NULL,NULL FROM taxa")
    op.execute(
        "CREATE TABLE taxonomy_changes (revision INTEGER PRIMARY KEY AUTOINCREMENT, "
        "taxon_id TEXT REFERENCES taxa(taxon_id), kind TEXT NOT NULL, "
        "recorded_at TEXT NOT NULL, details TEXT NOT NULL)"
    )
    op.execute(
        "CREATE TABLE taxonomy_generations (generation_id TEXT PRIMARY KEY, "
        "label TEXT NOT NULL, provider TEXT NOT NULL, source_url TEXT NOT NULL, "
        "retrieved_at TEXT NOT NULL, snapshot_at TEXT, imported_at TEXT NOT NULL, "
        "checksum TEXT NOT NULL, rights TEXT NOT NULL, starting_revision INTEGER NOT NULL, "
        "state TEXT NOT NULL CHECK(state IN ('staging','ready','retiring')), "
        "content_revision INTEGER NOT NULL DEFAULT 0)"
    )
    op.execute(
        "CREATE INDEX ix_taxonomy_public_changes ON taxonomy_changes(revision,taxon_id) "
        "WHERE kind NOT IN ('snapshot_identity_reserved','snapshot_labels')"
    )
    op.execute(
        "CREATE TABLE taxonomy_facts (generation_id TEXT NOT NULL REFERENCES "
        "taxonomy_generations(generation_id) ON DELETE CASCADE, taxon_id TEXT NOT NULL "
        "REFERENCES taxa(taxon_id), payload TEXT NOT NULL, search_rowid INTEGER, "
        "PRIMARY KEY(generation_id,taxon_id))"
    )
    op.execute(
        "CREATE TABLE taxonomy_generation_publications (generation_id TEXT PRIMARY KEY, "
        "provenance TEXT NOT NULL)"
    )
    op.execute(
        "CREATE INDEX ix_taxonomy_fact_provider ON taxonomy_facts "
        "(generation_id,json_extract(payload,'$.provider_id'))"
    )
    op.execute("CREATE INDEX ix_taxonomy_fact_taxon ON taxonomy_facts(taxon_id,generation_id)")
    op.execute(
        "CREATE TABLE taxonomy_overlay (taxon_id TEXT NOT NULL REFERENCES taxa(taxon_id), "
        "provider TEXT NOT NULL, payload TEXT NOT NULL, retrieved_at TEXT NOT NULL, "
        "source_effective_at TEXT, revision INTEGER NOT NULL REFERENCES "
        "taxonomy_changes(revision), PRIMARY KEY(taxon_id,provider))"
    )
    op.execute(
        "CREATE INDEX ix_taxonomy_overlay_name ON taxonomy_overlay "
        "(json_extract(payload,'$.accepted_scientific_name'),"
        "json_extract(payload,'$.supported_group'))"
    )
    op.execute(
        "CREATE INDEX ix_taxonomy_fact_name ON taxonomy_facts "
        "(generation_id,json_extract(payload,'$.accepted_scientific_name'),"
        "json_extract(payload,'$.supported_group'))"
    )
    op.execute(
        "CREATE TABLE taxonomy_selection (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
        "generation_id TEXT REFERENCES taxonomy_generations(generation_id), "
        "reconciled_revision INTEGER NOT NULL)"
    )
    op.execute("INSERT INTO taxonomy_selection VALUES(1,NULL,0)")
    op.execute(
        "CREATE TABLE taxonomy_conflicts (conflict_id INTEGER PRIMARY KEY, "
        "taxon_id TEXT NOT NULL REFERENCES taxa(taxon_id), kind TEXT NOT NULL, "
        "details TEXT NOT NULL, generation_id TEXT, "
        "resolved_at TEXT, decided_by TEXT, reason TEXT)"
    )
    op.execute(
        "CREATE INDEX ix_taxonomy_conflicts_open ON taxonomy_conflicts (generation_id,resolved_at)"
    )
    op.execute(
        "CREATE VIRTUAL TABLE taxonomy_search USING fts5(taxon_id UNINDEXED, "
        "scope UNINDEXED, names, workflow_groups, "
        "tokenize='unicode61 remove_diacritics 2', prefix='2 3 4')"
    )
    legacy_labels = " || ' ' || ".join(
        "coalesce(t." + field + ",'')"
        for field in (
            "accepted_scientific_name",
            "preferred_common_name",
            "authorship",
            "rank",
            "kingdom",
            "phylum_division",
            "class_name",
            "order_name",
            "family",
            "genus",
            "species",
            "infra_rank",
        )
    )
    op.execute(
        "INSERT INTO taxonomy_search(taxon_id,scope,names,workflow_groups) "
        "SELECT t.taxon_id,'catalog',"
        + legacy_labels
        + " || ' ' || coalesce(group_concat(n.name,' '),''),t.supported_group "
        "FROM taxa t LEFT JOIN taxon_names n USING(taxon_id) GROUP BY t.taxon_id"
    )
    op.execute(
        "CREATE TABLE taxonomy_search_keys (taxon_id TEXT PRIMARY KEY REFERENCES taxa(taxon_id), "
        "search_rowid INTEGER NOT NULL UNIQUE)"
    )
    op.execute(
        "INSERT INTO taxonomy_search_keys SELECT taxon_id,rowid FROM taxonomy_search "
        "WHERE scope='catalog'"
    )
    op.execute(
        "CREATE TRIGGER taxa_identity_no_rekey BEFORE UPDATE OF taxon_id ON taxa "
        "WHEN NEW.taxon_id != OLD.taxon_id BEGIN SELECT RAISE(ABORT,'permanent taxon "
        "identity'); END"
    )
    # Guard every permanent identity, including unreferenced reservations. Cleanup is
    # reference-only.
    op.execute(
        "CREATE TRIGGER taxa_identity_no_delete BEFORE DELETE ON taxa "
        "BEGIN SELECT RAISE(ABORT,'permanent taxon identity'); END"
    )
    op.execute(
        "CREATE TRIGGER taxon_mapping_no_relink BEFORE UPDATE OF taxon_id,provider,provider_id "
        "ON taxon_provider_mappings WHEN NEW.taxon_id IS NOT OLD.taxon_id "
        "OR NEW.provider IS NOT OLD.provider OR NEW.provider_id IS NOT OLD.provider_id "
        "BEGIN SELECT RAISE(ABORT,'permanent provider mapping'); END"
    )
    op.execute(
        "CREATE TRIGGER taxon_mapping_no_delete BEFORE DELETE ON taxon_provider_mappings "
        "BEGIN SELECT RAISE(ABORT,'permanent provider mapping'); END"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if (
        bind.execute(sa.text("SELECT 1 FROM taxonomy_changes LIMIT 1")).first()
        or bind.execute(sa.text("SELECT 1 FROM taxonomy_generations LIMIT 1")).first()
        or bind.execute(sa.text("SELECT 1 FROM taxonomy_conflicts LIMIT 1")).first()
    ):
        raise RuntimeError(
            "Taxonomy downgrade blocked: durable X2 data exists; use forward recovery."
        )
    for trigger in (
        "taxa_identity_no_delete",
        "taxa_identity_no_rekey",
        "taxon_mapping_no_relink",
        "taxon_mapping_no_delete",
    ):
        op.execute(f"DROP TRIGGER {trigger}")
    for table in (
        "taxonomy_generation_publications",
        "taxonomy_search_keys",
        "taxonomy_search",
        "taxonomy_conflicts",
        "taxonomy_selection",
        "taxonomy_overlay",
        "taxonomy_facts",
        "taxonomy_generations",
        "taxonomy_changes",
        "taxonomy_publications",
    ):
        op.drop_table(table)
    with op.batch_alter_table("taxa", recreate="always") as batch:
        batch.drop_column("taxonomy_provider")
        batch.drop_constraint("ck_taxa_status", type_="check")
        batch.create_check_constraint(
            "ck_taxa_status", "taxonomic_status IN ('accepted','synonym','unknown')"
        )
        batch.create_check_constraint(
            "ck_taxa_supported_group",
            "supported_group IN ('snake','lizard','spider','scorpion','plant')",
        )
