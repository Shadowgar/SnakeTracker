"""Bounded, explicit cross-household reads for platform support."""

# SQL query clauses remain on one line so they can be compared with query plans.
# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from snaketracker.application.admin import PAGE_SIZE
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage


class AdminReadRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(sql), params).mappings()]

    def one(self, sql: str, **params: Any) -> dict[str, Any] | None:
        rows = self.rows(sql, **params)
        return rows[0] if rows else None

    def audit(
        self,
        *,
        actor: UUID | None,
        action: str,
        outcome: str,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> None:
        # No query text, payload, network context, or secrets enter this log.
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO security_audit "
                    "(audit_id,recorded_at,category,action,outcome,actor_user_id,"
                    "household_id,target_type,target_id,correlation_id,details_json) "
                    "VALUES (:audit_id,:recorded_at,'platform_admin',:action,:outcome,"
                    ":actor,NULL,:target_type,:target_id,:correlation_id,'{}')"
                ),
                {
                    "audit_id": str(uuid4()),
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "action": action,
                    "outcome": outcome,
                    "actor": str(actor) if actor else None,
                    "target_type": target_type,
                    "target_id": target_id if target_id and len(target_id) <= 36 else None,
                    "correlation_id": str(uuid4()),
                },
            )

    def overview(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        return (
            self.one(
                "SELECT (SELECT count(*) FROM users) accounts,"
                "(SELECT count(*) FROM users WHERE status='active') active_accounts,"
                "(SELECT count(*) FROM household_summaries) households,"
                "(SELECT count(*) FROM authorization_memberships) memberships,"
                "(SELECT count(*) FROM animal_current) animals,"
                "(SELECT count(*) FROM enclosure_current) enclosures,"
                "(SELECT count(*) FROM enclosure_plant_current) plants,"
                "(SELECT count(*) FROM inventory_balance) inventory,"
                "(SELECT count(*) FROM domain_events) events,"
                "(SELECT coalesce(max(global_position),0) FROM domain_events) high_water,"
                "(SELECT count(*) FROM jobs WHERE status IN ('pending','retry')) pending_jobs,"
                "(SELECT count(*) FROM jobs WHERE status IN ('dead_letter','reconciliation_required')) failed_jobs,"
                "(SELECT max(updated_at) FROM jobs WHERE status IN ('dead_letter','reconciliation_required')) latest_failed_job,"
                "(SELECT max(completed_at) FROM backup_runs WHERE status='completed') latest_completed_backup,"
                "(SELECT round((julianday('now')-julianday(max(completed_at)))*24,1) FROM backup_runs WHERE status='completed') backup_age_hours,"
                "(SELECT version_num FROM alembic_version LIMIT 1) migration_revision,"
                "(SELECT max(created_at) FROM users) latest_registration,"
                "(SELECT count(*) FROM users WHERE created_at>=:week) registrations_7d,"
                "(SELECT count(*) FROM users WHERE created_at>=:month) registrations_30d,"
                "(SELECT max(created_at) FROM household_summaries) latest_household,"
                "(SELECT max(recorded_at) FROM domain_events WHERE event_type NOT IN "
                "('inventory.stock_consumed','inventory.consumption_reversed')) latest_event,"
                "(SELECT count(*) FROM domain_events WHERE recorded_at>=:day) events_24h",
                day=(now - timedelta(days=1)).isoformat(),
                week=(now - timedelta(days=7)).isoformat(),
                month=(now - timedelta(days=30)).isoformat(),
            )
            or {}
        )

    def search(self, query: str) -> dict[str, list[dict[str, Any]]]:
        value = query.strip()[:120]
        if not value:
            return {}
        try:
            exact_uuid = str(UUID(value))
        except ValueError:
            exact_uuid = None
        like = f"%{value.replace('%', '').replace('_', '')}%"
        specs = {
            "Accounts": ("users", "user_id", "display_name", "email_normalized"),
            "Households": ("household_summaries", "household_id", "name", "timezone"),
            "Animals": ("animal_current", "animal_id", "name", "species"),
            "Enclosures": ("enclosure_current", "enclosure_id", "name", "enclosure_type"),
            "Inventory": ("inventory_balance", "item_id", "name", "unit"),
        }
        found: dict[str, list[dict[str, Any]]] = {}
        for group, (table, key, label, secondary) in specs.items():
            if exact_uuid:
                found[group] = self.rows(
                    f"SELECT {key} id,{label} label,{secondary} secondary "
                    f"FROM {table} WHERE {key}=:exact LIMIT 1",
                    exact=exact_uuid,
                )
            elif group == "Households":
                found[group] = self.rows(
                    "SELECT h.household_id id,h.name label,h.timezone secondary "
                    "FROM household_summaries h WHERE h.name LIKE :like OR EXISTS "
                    "(SELECT 1 FROM authorization_memberships m JOIN users u USING(user_id) "
                    "WHERE m.household_id=h.household_id AND "
                    "(u.email_normalized LIKE :like OR u.display_name LIKE :like)) "
                    "ORDER BY h.name LIMIT 12",
                    like=like,
                )
            else:
                found[group] = self.rows(
                    f"SELECT {key} id,{label} label,{secondary} secondary "
                    f"FROM {table} WHERE {label} LIKE :like OR {secondary} LIKE :like "
                    f"ORDER BY {label} LIMIT 12",
                    like=like,
                )
        found["Events"] = self.rows(
            "SELECT event_id id,title label,event_type secondary FROM domain_events "
            "WHERE event_id=:exact LIMIT 1",
            exact=exact_uuid or value,
        )
        if not found["Events"] and exact_uuid:
            found["Events"] = self.rows(
                "SELECT event_id id,title label,event_type secondary FROM domain_events "
                "WHERE correlation_id=:exact ORDER BY global_position DESC LIMIT 12",
                exact=exact_uuid,
            )
        return found

    def accounts(
        self,
        query: str,
        status: str,
        household: str,
        role: str,
        registered_from: str,
        registered_before: str,
        page: int,
    ) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT u.user_id,u.display_name,u.email_normalized,u.status,u.created_at,"
            "count(m.household_id) membership_count,group_concat(h.name || ' (' || m.role || ')', ', ') households,"
            "(SELECT max(a.recorded_at) FROM security_audit a "
            "WHERE a.actor_user_id=u.user_id AND a.category!='platform_admin') last_activity "
            "FROM users u LEFT JOIN authorization_memberships m ON m.user_id=u.user_id "
            "LEFT JOIN household_summaries h ON h.household_id=m.household_id "
            "WHERE (:status='' OR u.status=:status) "
            "AND (:query='' OR u.user_id=:query OR u.email_normalized LIKE :like OR u.display_name LIKE :like) "
            "AND (:household='' OR EXISTS (SELECT 1 FROM authorization_memberships x WHERE x.user_id=u.user_id AND x.household_id=:household)) "
            "AND (:role='' OR EXISTS (SELECT 1 FROM authorization_memberships x WHERE x.user_id=u.user_id AND x.role=:role)) "
            "AND (:registered_from='' OR u.created_at>=:registered_from) "
            "AND (:registered_before='' OR u.created_at<:registered_before) "
            "GROUP BY u.user_id ORDER BY u.created_at DESC,u.user_id LIMIT :limit OFFSET :offset",
            status=status,
            query=query,
            like=f"%{query}%",
            household=household,
            role=role,
            registered_from=registered_from,
            registered_before=registered_before,
            limit=PAGE_SIZE + 1,
            offset=(page - 1) * PAGE_SIZE,
        )

    def account(self, user_id: str) -> dict[str, Any] | None:
        return self.one(
            "SELECT user_id,display_name,email_normalized,status,created_at FROM users WHERE user_id=:id",
            id=user_id,
        )

    def memberships(self, user_id: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT m.household_id,m.role,m.status,m.updated_at,h.name "
            "FROM authorization_memberships m JOIN household_summaries h USING (household_id) "
            "WHERE m.user_id=:id ORDER BY h.name LIMIT 100",
            id=user_id,
        )

    def sessions(self, user_id: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT session_id,created_at,last_seen_at,idle_expires_at,absolute_expires_at,"
            "revoked_at,user_agent_class FROM sessions WHERE user_id=:id "
            "ORDER BY created_at DESC LIMIT 30",
            id=user_id,
        )

    def account_audit(self, user_id: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT recorded_at,action,outcome FROM security_audit WHERE actor_user_id=:id "
            "AND category!='platform_admin' ORDER BY recorded_at DESC LIMIT 30",
            id=user_id,
        )

    def households(self, query: str, page: int) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT h.household_id,h.name,h.timezone,h.created_at,"
            "(SELECT count(*) FROM authorization_memberships m WHERE m.household_id=h.household_id) members,"
            "(SELECT count(*) FROM animal_current a WHERE a.household_id=h.household_id) animals,"
            "(SELECT count(*) FROM enclosure_current e WHERE e.household_id=h.household_id) enclosures,"
            "(SELECT count(*) FROM enclosure_plant_current p WHERE p.household_id=h.household_id) plants,"
            "(SELECT count(*) FROM inventory_balance i WHERE i.household_id=h.household_id) inventory,"
            "(SELECT count(*) FROM domain_events d WHERE d.household_id=h.household_id) events,"
            "(SELECT max(recorded_at) FROM domain_events d WHERE d.household_id=h.household_id) latest_activity "
            "FROM household_summaries h WHERE :query='' OR h.household_id=:query OR h.name LIKE :like "
            "OR EXISTS (SELECT 1 FROM authorization_memberships m JOIN users u USING(user_id) "
            "WHERE m.household_id=h.household_id AND (u.email_normalized LIKE :like OR u.display_name LIKE :like)) "
            "ORDER BY h.created_at DESC LIMIT :limit OFFSET :offset",
            query=query,
            like=f"%{query}%",
            limit=PAGE_SIZE + 1,
            offset=(page - 1) * PAGE_SIZE,
        )

    def household(self, household_id: str) -> dict[str, Any] | None:
        return self.one(
            "SELECT household_id,name,timezone,created_at FROM household_summaries WHERE household_id=:id",
            id=household_id,
        )

    def household_bundle(self, household_id: str) -> dict[str, list[dict[str, Any]]]:
        id = household_id
        return {
            "members": self.rows(
                "SELECT u.user_id,u.display_name,u.email_normalized,u.status account_status,m.role,m.status FROM authorization_memberships m JOIN users u USING(user_id) WHERE m.household_id=:id ORDER BY m.role,u.display_name LIMIT 100",
                id=id,
            ),
            "animals": self.rows(
                "SELECT a.animal_id,a.name,a.animal_type,a.species,a.status,a.current_enclosure_id,"
                "e.name enclosure_name,"
                "(SELECT count(*) FROM domain_events d WHERE d.household_id=a.household_id "
                "AND d.stream_type='animal' AND d.stream_id=a.animal_id) event_count,"
                "(SELECT d.title FROM domain_events d WHERE d.household_id=a.household_id "
                "AND d.stream_type='animal' AND d.stream_id=a.animal_id "
                "AND d.event_type IN ('animal.feeding_recorded','animal.feeding_corrected',"
                "'animal.weight_recorded','animal.weight_corrected','animal.shed_recorded',"
                "'animal.molt_recorded','animal.bath_recorded') "
                "ORDER BY d.stream_version DESC LIMIT 1) latest_care "
                "FROM animal_current a LEFT JOIN enclosure_current e ON e.household_id=a.household_id "
                "AND e.enclosure_id=a.current_enclosure_id "
                "WHERE a.household_id=:id ORDER BY a.name LIMIT 100",
                id=id,
            ),
            "enclosures": self.rows(
                "SELECT e.enclosure_id,e.name,e.enclosure_type,e.status,"
                "(SELECT count(*) FROM animal_current a WHERE a.household_id=e.household_id "
                "AND a.current_enclosure_id=e.enclosure_id) occupants,"
                "(SELECT count(*) FROM enclosure_plant_current p WHERE p.household_id=e.household_id "
                "AND p.enclosure_id=e.enclosure_id AND p.status='active') plants,"
                "(SELECT d.title FROM domain_events d WHERE d.household_id=e.household_id "
                "AND d.stream_type='enclosure' AND d.stream_id=e.enclosure_id "
                "AND d.event_type IN ('enclosure.cleaning_recorded',"
                "'enclosure.water_change_recorded','enclosure.misting_recorded') "
                "ORDER BY d.stream_version DESC LIMIT 1) latest_maintenance "
                "FROM enclosure_current e WHERE e.household_id=:id ORDER BY e.name LIMIT 100",
                id=id,
            ),
            "plants": self.rows(
                "SELECT enclosure_plant_id,enclosure_id,coalesce(label,confirmed_common_name,confirmed_scientific_name,manual_species) name,status FROM enclosure_plant_current WHERE household_id=:id ORDER BY name LIMIT 100",
                id=id,
            ),
            "inventory": self.rows(
                "SELECT item_id,name,status,on_hand_quantity_scaled,reorder_threshold_scaled,unit_code FROM inventory_balance WHERE household_id=:id ORDER BY name LIMIT 100",
                id=id,
            ),
            "events": self.rows(
                "SELECT event_id,title,event_type,occurred_at FROM domain_events WHERE household_id=:id ORDER BY global_position DESC LIMIT 20",
                id=id,
            ),
            "jobs": self.rows(
                "SELECT job_id,job_type,status,safe_error FROM jobs WHERE household_id=:id AND status IN ('dead_letter','reconciliation_required') ORDER BY updated_at DESC LIMIT 10",
                id=id,
            ),
        }

    def household_financial(self, household_id: str) -> dict[str, Any]:
        return (
            self.one(
                "SELECT (SELECT count(*) FROM purchase_current WHERE household_id=:id) purchases,"
                "(SELECT count(*) FROM expense_current WHERE household_id=:id) expenses,"
                "(SELECT max(occurred_at) FROM purchase_current WHERE household_id=:id) latest_purchase,"
                "(SELECT max(occurred_at) FROM expense_current WHERE household_id=:id) latest_expense",
                id=household_id,
            )
            or {}
        )

    def subject(self, table: str, key: str, identifier: str) -> dict[str, Any] | None:
        # Callers select from fixed server-owned table/column constants.
        return self.one(f"SELECT * FROM {table} WHERE {key}=:id", id=identifier)

    def subject_events(
        self, household_id: str, subject_type: str, subject_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT e.event_id,e.title,e.event_type,e.schema_version,e.occurred_at,e.recorded_at,"
            "e.actor_user_id,e.correlation_id,e.causation_id,e.stream_type,e.stream_id,e.stream_version "
            "FROM domain_events e JOIN event_subjects s ON s.event_id=e.event_id "
            "WHERE e.household_id=:household AND s.subject_type=:type AND s.subject_id=:id "
            "ORDER BY e.global_position DESC LIMIT :limit",
            household=household_id,
            type=subject_type,
            id=subject_id,
            limit=limit,
        )

    def events(self, query: str, field: str, page: int) -> list[dict[str, Any]]:
        columns = {
            "event_id": "e.event_id",
            "event_type": "e.event_type",
            "correlation_id": "e.correlation_id",
            "causation_id": "e.causation_id",
            "actor_user_id": "e.actor_user_id",
            "household_id": "e.household_id",
            "animal_id": "s.subject_id",
            "inventory_id": "s.subject_id",
        }
        column = columns.get(field, "e.event_id")
        join = (
            "JOIN event_subjects s ON s.event_id=e.event_id "
            if field in {"animal_id", "inventory_id"}
            else ""
        )
        type_clause = "AND s.subject_type=:subject_type " if join else ""
        return self.rows(
            "SELECT e.event_id,e.title,e.event_type,e.occurred_at,e.actor_user_id,e.household_id,e.correlation_id "
            f"FROM domain_events e {join}WHERE (:query='' OR {column}=:query "
            f"OR {column} LIKE :like) {type_clause}ORDER BY e.global_position DESC "
            "LIMIT :limit OFFSET :offset",
            query=query,
            like=f"%{query}%",
            subject_type="animal" if field == "animal_id" else "inventory_item",
            limit=PAGE_SIZE + 1,
            offset=(page - 1) * PAGE_SIZE,
        )

    def event(self, event_id: str) -> dict[str, Any] | None:
        return self.one(
            "SELECT event_id,global_position,household_id,stream_type,stream_id,stream_version,"
            "event_type,schema_version,title,occurred_at,recorded_at,actor_user_id,correlation_id,"
            "causation_id,payload_json FROM domain_events WHERE event_id=:id",
            id=event_id,
        )

    def event_subjects(self, event_id: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT subject_type,subject_id,relationship FROM event_subjects WHERE event_id=:id ORDER BY display_order LIMIT 30",
            id=event_id,
        )

    def event_relations(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT event_id,title,event_type,occurred_at FROM domain_events WHERE household_id=:household "
            "AND event_id!=:id AND (correlation_id=:correlation OR causation_id=:id OR event_id=:causation) "
            "ORDER BY global_position LIMIT 50",
            household=event["household_id"],
            id=event["event_id"],
            correlation=event["correlation_id"],
            causation=event["causation_id"],
        )

    def inventory_links(self, item_id: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT l.source_event_id,l.consumption_event_id,l.quantity_scaled,l.status,l.reversal_event_id,"
            "e.event_type source_type,e.title source_title,e.actor_user_id,e.occurred_at,"
            "s.subject_id animal_id,a.name animal_name "
            "FROM inventory_consumption_links_v2 l LEFT JOIN domain_events e ON e.event_id=l.source_event_id "
            "LEFT JOIN event_subjects s ON s.event_id=e.event_id AND s.subject_type='animal' "
            "LEFT JOIN animal_current a ON a.animal_id=s.subject_id AND a.household_id=l.household_id "
            "WHERE l.item_id=:id ORDER BY e.recorded_at DESC LIMIT 100",
            id=item_id,
        )

    def animal_inventory_links(self, animal_id: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT l.source_event_id,l.consumption_event_id,l.item_id,l.quantity_scaled,"
            "l.status,i.name item_name,e.occurred_at,e.actor_user_id "
            "FROM event_subjects s JOIN inventory_consumption_links_v2 l "
            "ON l.source_event_id=s.event_id "
            "LEFT JOIN inventory_balance i ON i.household_id=l.household_id AND i.item_id=l.item_id "
            "LEFT JOIN domain_events e ON e.event_id=l.source_event_id "
            "WHERE s.subject_type='animal' AND s.subject_id=:id "
            "ORDER BY e.recorded_at DESC LIMIT 100",
            id=animal_id,
        )

    def incident_identity(self, value: str) -> tuple[str, dict[str, Any]] | None:
        for kind, sql in (
            (
                "account",
                "SELECT user_id,display_name,email_normalized FROM users WHERE user_id=:value OR email_normalized=:value LIMIT 1",
            ),
            (
                "household",
                "SELECT household_id,name FROM household_summaries WHERE household_id=:value LIMIT 1",
            ),
            (
                "animal",
                "SELECT animal_id,household_id,name,species FROM animal_current WHERE animal_id=:value LIMIT 1",
            ),
            (
                "enclosure",
                "SELECT enclosure_id,household_id,name FROM enclosure_current WHERE enclosure_id=:value LIMIT 1",
            ),
            (
                "inventory",
                "SELECT item_id,household_id,name FROM inventory_balance WHERE item_id=:value LIMIT 1",
            ),
            (
                "event",
                "SELECT event_id,household_id,title,correlation_id FROM domain_events WHERE event_id=:value LIMIT 1",
            ),
        ):
            item = self.one(sql, value=value)
            if item is not None:
                return kind, item
        group = self.one(
            "SELECT event_id,household_id,title,correlation_id FROM domain_events "
            "WHERE correlation_id=:value ORDER BY global_position DESC LIMIT 1",
            value=value,
        )
        return ("correlation", group) if group else None

    def subject_exists(self, household_id: str, subject_type: str, subject_id: str) -> bool | None:
        targets = {
            "household": ("household_summaries", "household_id"),
            "animal": ("animal_current", "animal_id"),
            "enclosure": ("enclosure_current", "enclosure_id"),
            "inventory_item": ("inventory_balance", "item_id"),
            "enclosure-plant": ("enclosure_plant_current", "enclosure_plant_id"),
        }
        if subject_type == "user":
            return (
                self.one(
                    "SELECT 1 FROM authorization_memberships WHERE household_id=:household "
                    "AND user_id=:id LIMIT 1",
                    household=household_id,
                    id=subject_id,
                )
                is not None
            )
        target = targets.get(subject_type)
        if target is None:
            return None
        table, key = target
        return (
            self.one(
                f"SELECT 1 FROM {table} WHERE household_id=:household AND {key}=:id LIMIT 1",
                household=household_id,
                id=subject_id,
            )
            is not None
        )

    def system(self) -> dict[str, Any]:
        return {
            "revision": self.one("SELECT version_num FROM alembic_version LIMIT 1"),
            "jobs": self.rows("SELECT status,count(*) count FROM jobs GROUP BY status"),
            "failures": self.rows(
                "SELECT job_id,job_type,household_id,safe_error,updated_at FROM jobs WHERE status IN ('dead_letter','reconciliation_required') ORDER BY updated_at DESC LIMIT 20"
            ),
            "backup": self.one(
                "SELECT run_id,completed_at,status FROM backup_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
            ),
            "backup_failures": self.rows(
                "SELECT run_id,completed_at,error_message FROM backup_runs WHERE status='failed' ORDER BY completed_at DESC LIMIT 10"
            ),
            "attachments": self.one("SELECT count(*) count FROM attachment_versions"),
            "projections": self.rows(
                "SELECT projection_name,consistency_class,active_generation_id FROM projection_definitions ORDER BY projection_name LIMIT 40"
            ),
        }

    def storage_health(self, attachment_root: Path, reference_root: Path) -> dict[str, Any]:
        metadata = self.rows("SELECT storage_key,media_type FROM attachment_versions")
        files = LocalAttachmentStorage(attachment_root).finalized_storage_keys()
        expected = {(UUID(item["storage_key"]), item["media_type"]) for item in metadata}
        missing_reference = self.one(
            "SELECT count(*) count FROM animal_current a LEFT JOIN attachment_versions v "
            "ON v.attachment_version_id=a.photo_attachment_version_id "
            "WHERE a.photo_attachment_version_id IS NOT NULL AND v.attachment_version_id IS NULL"
        )
        references = self.one(
            "SELECT count(*) count FROM animal_current WHERE photo_attachment_version_id IS NOT NULL"
        )
        images = self.rows(
            "SELECT local_filename,provider FROM taxon_images WHERE local_filename IS NOT NULL"
        )
        missing_images = sum(
            1
            for item in images
            if not item["local_filename"].endswith(".webp")
            or Path(item["local_filename"]).name != item["local_filename"]
            or not (reference_root / item["local_filename"]).is_file()
        )
        return {
            "attachment_files": len(files),
            "attachment_references": references["count"] if references else 0,
            "missing_attachment_references": missing_reference["count"] if missing_reference else 0,
            "missing_attachment_files": len(expected - files),
            "reference_images": len(images),
            "missing_reference_images": missing_images,
            "reference_providers": sorted({item["provider"] for item in images}),
        }

    def audit_rows(
        self,
        operator: str,
        action: str,
        target_type: str,
        target_id: str,
        since: str,
        until: str,
        page: int,
    ) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT recorded_at,actor_user_id,action,target_type,target_id,outcome FROM security_audit "
            "WHERE category='platform_admin' AND (:operator='' OR actor_user_id=:operator) "
            "AND (:action='' OR action=:action) AND (:target_type='' OR target_type=:target_type) "
            "AND (:target_id='' OR target_id=:target_id) AND (:since='' OR recorded_at>=:since) "
            "AND (:until='' OR recorded_at<:until) ORDER BY recorded_at DESC LIMIT :limit OFFSET :offset",
            operator=operator,
            action=action,
            target_type=target_type,
            target_id=target_id,
            since=since,
            until=until,
            limit=PAGE_SIZE + 1,
            offset=(page - 1) * PAGE_SIZE,
        )
