"""Read-only platform support console; household roles never authorize it."""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from snaketracker.application.admin import PAGE_SIZE, AdminEventReadPort, AdminReadPort
from snaketracker.application.animals import AnimalService
from snaketracker.application.enclosures import EnclosureService
from snaketracker.application.identity import AuthenticationError, IdentityService, Principal
from snaketracker.platform.events.corrections import evaluate_effective_events
from snaketracker.platform.events.store import StreamKey
from snaketracker.presentation.animal_care_views import present_effective_care_events
from snaketracker.presentation.web import SESSION_COOKIE, templates

PLATFORM_READ_CAPABILITIES = frozenset(
    {"platform.admin.read", "platform.support.read", "platform.system.read"}
)


def create_admin_router(
    *,
    repository: AdminReadPort,
    identity: IdentityService,
    operator_ids: frozenset[UUID],
    animals: AnimalService,
    enclosures: EnclosureService,
    event_store: AdminEventReadPort,
    environment: str,
    version: str,
    attachment_root: Path,
    reference_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/admin", include_in_schema=False)

    def access(
        request: Request, action: str, target_type: str | None = None, target_id: str | None = None
    ) -> tuple[Principal | None, HTMLResponse | None]:
        principal: Principal | None = None
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            with suppress(AuthenticationError):
                principal = identity.authenticate(token)
        permitted = principal is not None and principal.user_id in operator_ids
        repository.audit(
            actor=principal.user_id if principal else None,
            action=action,
            outcome="success" if permitted else "denied",
            target_type=target_type,
            target_id=target_id,
        )
        if not permitted:
            return None, HTMLResponse("Access denied", status_code=403)
        return principal, None

    def page(request: Request, title: str, principal: Principal, **data: object) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                "title": title,
                "operator": principal,
                "capabilities": PLATFORM_READ_CAPABILITIES,
                **data,
            },
            headers={"Cache-Control": "private, no-store"},
        )

    def pagination(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], bool]:
        return rows[:PAGE_SIZE], len(rows) > PAGE_SIZE

    @router.get("", response_class=HTMLResponse)
    def overview(request: Request, q: str = "") -> HTMLResponse:
        principal, denial = access(request, "admin.overview.view")
        if denial:
            return denial
        assert principal is not None
        return page(
            request,
            "Overview",
            principal,
            kind="overview",
            summary=repository.overview(),
            storage=repository.storage_health(attachment_root, reference_root),
            search=repository.search(q),
            q=q[:120],
            version=version,
        )

    @router.get("/accounts", response_class=HTMLResponse)
    def accounts(
        request: Request,
        q: str = "",
        status: str = "",
        household: str = "",
        role: str = "",
        registered_from: date | None = None,
        registered_before: date | None = None,
        p: int = 1,
    ) -> HTMLResponse:
        principal, denial = access(request, "admin.accounts.list")
        if denial:
            return denial
        assert principal is not None
        p = max(1, min(p, 10000))
        status = status if status in {"active", "disabled"} else ""
        role = role if role in {"owner", "administrator", "caretaker", "viewer"} else ""
        rows, more = pagination(
            repository.accounts(
                q[:120],
                status,
                household[:36],
                role,
                registered_from.isoformat() if registered_from else "",
                registered_before.isoformat() if registered_before else "",
                p,
            )
        )
        return page(
            request,
            "Accounts",
            principal,
            kind="accounts",
            rows=rows,
            more=more,
            p=p,
            q=q[:120],
            status=status,
            role=role,
            household=household[:36],
            registered_from=registered_from.isoformat() if registered_from else "",
            registered_before=registered_before.isoformat() if registered_before else "",
        )

    @router.get("/accounts/{user_id}", response_class=HTMLResponse)
    def account(request: Request, user_id: UUID) -> HTMLResponse:
        principal, denial = access(request, "admin.account.view", "account", str(user_id))
        if denial:
            return denial
        assert principal is not None
        record = repository.account(str(user_id))
        if record is None:
            return HTMLResponse("Account not found", status_code=404)
        return page(
            request,
            "Account detail",
            principal,
            kind="account",
            record=record,
            memberships=repository.memberships(str(user_id)),
            sessions=repository.sessions(str(user_id)),
            security=repository.account_audit(str(user_id)),
            activity=repository.events(str(user_id), "actor_user_id", 1)[:20],
        )

    @router.get("/households", response_class=HTMLResponse)
    def households(request: Request, q: str = "", p: int = 1) -> HTMLResponse:
        principal, denial = access(request, "admin.households.list")
        if denial:
            return denial
        assert principal is not None
        p = max(1, min(p, 10000))
        rows, more = pagination(repository.households(q[:120], p))
        return page(
            request,
            "Households",
            principal,
            kind="households",
            rows=rows,
            more=more,
            p=p,
            q=q[:120],
        )

    @router.get("/households/{household_id}", response_class=HTMLResponse)
    def household(request: Request, household_id: UUID) -> HTMLResponse:
        principal, denial = access(request, "admin.household.view", "household", str(household_id))
        if denial:
            return denial
        assert principal is not None
        record = repository.household(str(household_id))
        if record is None:
            return HTMLResponse("Household not found", status_code=404)
        return page(
            request,
            "Household support",
            principal,
            kind="household",
            record=record,
            bundle=repository.household_bundle(str(household_id)),
            financial=repository.household_financial(str(household_id)),
        )

    @router.get("/animals/{animal_id}", response_class=HTMLResponse)
    def animal(request: Request, animal_id: UUID) -> HTMLResponse:
        principal, denial = access(request, "admin.animal.support_view", "animal", str(animal_id))
        if denial:
            return denial
        assert principal is not None
        record = repository.subject("animal_current", "animal_id", str(animal_id))
        if record is None:
            return HTMLResponse("Animal not found", status_code=404)
        household_id = UUID(record["household_id"])
        profile = animals.profile_for(household_id, animal_id)
        history = (
            present_effective_care_events(animals.effective_history(household_id, animal_id))
            if profile is not None
            else ()
        )
        events = repository.subject_events(str(household_id), "animal", str(animal_id))
        return page(
            request,
            "Animal support",
            principal,
            kind="animal",
            record=record,
            history=history[:100],
            events=events,
            truncated=len(history) > 100 or len(events) == 100,
        )

    @router.get("/enclosures/{enclosure_id}", response_class=HTMLResponse)
    def enclosure(request: Request, enclosure_id: UUID) -> HTMLResponse:
        principal, denial = access(
            request, "admin.enclosure.support_view", "enclosure", str(enclosure_id)
        )
        if denial:
            return denial
        assert principal is not None
        record = repository.subject("enclosure_current", "enclosure_id", str(enclosure_id))
        if record is None:
            return HTMLResponse("Enclosure not found", status_code=404)
        household_id = UUID(record["household_id"])
        history = enclosures.effective_history(household_id, enclosure_id)
        bundle = repository.household_bundle(str(household_id))
        return page(
            request,
            "Enclosure support",
            principal,
            kind="enclosure",
            record=record,
            history=history[:100],
            events=repository.subject_events(str(household_id), "enclosure", str(enclosure_id)),
            occupants=[
                item
                for item in bundle["animals"]
                if item["current_enclosure_id"] == str(enclosure_id)
            ],
            plants=[item for item in bundle["plants"] if item["enclosure_id"] == str(enclosure_id)],
        )

    @router.get("/inventory/{item_id}", response_class=HTMLResponse)
    def inventory(request: Request, item_id: UUID) -> HTMLResponse:
        principal, denial = access(
            request, "admin.inventory.support_view", "inventory_item", str(item_id)
        )
        if denial:
            return denial
        assert principal is not None
        record = repository.subject("inventory_balance", "item_id", str(item_id))
        if record is None:
            return HTMLResponse("Item not found", status_code=404)
        return page(
            request,
            "Inventory support",
            principal,
            kind="inventory",
            record=record,
            events=repository.subject_events(
                record["household_id"], "inventory_item", str(item_id)
            ),
            links=repository.inventory_links(str(item_id)),
        )

    @router.get("/events", response_class=HTMLResponse)
    def events(request: Request, q: str = "", field: str = "event_id", p: int = 1) -> HTMLResponse:
        principal, denial = access(request, "admin.event.search")
        if denial:
            return denial
        assert principal is not None
        p = max(1, min(p, 10000))
        field = (
            field
            if field
            in {
                "event_id",
                "event_type",
                "correlation_id",
                "causation_id",
                "actor_user_id",
                "household_id",
                "animal_id",
                "inventory_id",
            }
            else "event_id"
        )
        rows, more = pagination(repository.events(q[:120], field, p))
        return page(
            request,
            "Event inspector",
            principal,
            kind="events",
            rows=rows,
            more=more,
            p=p,
            q=q[:120],
            field=field,
        )

    @router.get("/events/{event_id}", response_class=HTMLResponse)
    def event(request: Request, event_id: UUID) -> HTMLResponse:
        principal, denial = access(request, "admin.event.view", "event", str(event_id))
        if denial:
            return denial
        assert principal is not None
        record = repository.event(str(event_id))
        if record is None:
            return HTMLResponse("Event not found", status_code=404)
        subjects = repository.event_subjects(str(event_id))
        relations = repository.event_relations(record)
        payload = json.loads(record.pop("payload_json"))
        target = payload.get("target_event_id") if isinstance(payload, dict) else None
        source = payload.get("source_event_id") if isinstance(payload, dict) else None
        warnings = []
        for label, identifier in (("Target event", target), ("Source event", source)):
            if identifier:
                related = repository.event(str(identifier))
                if related is None:
                    warnings.append(f"{label} is missing: {identifier}")
                elif related["household_id"] != record["household_id"]:
                    warnings.append(f"{label} crosses households: {identifier}")
        if record["causation_id"]:
            cause = repository.event(record["causation_id"])
            if cause is None:
                warnings.append("Causation event is missing")
            elif cause["household_id"] != record["household_id"]:
                warnings.append("Causation event crosses households")
        for subject in subjects:
            if (
                repository.subject_exists(
                    record["household_id"], subject["subject_type"], subject["subject_id"]
                )
                is False
            ):
                warnings.append(
                    f"{subject['subject_type']} subject does not resolve: {subject['subject_id']}"
                )
        if record["event_type"] == "inventory.stock_consumed" and source:
            feeding = repository.event(str(source))
            if feeding and not feeding["event_type"].startswith("animal.feeding_"):
                warnings.append("Inventory consumption source is not a Feeding")
        stream = event_store.load_stream(
            StreamKey(
                UUID(record["household_id"]), record["stream_type"], UUID(record["stream_id"])
            )
        )
        effective_ids = {item.event_id for item in evaluate_effective_events(stream)}
        controls = [
            item for item in stream if getattr(item.payload, "target_event_id", None) == event_id
        ]
        if record["event_type"].startswith("inventory.stock_"):
            state = "Internal side effect"
        elif record["event_type"] in {"event.voided", "event.reinstated"}:
            state = "Immutable control event"
        elif event_id in effective_ids:
            state = "Currently effective"
        elif any(item.event_type == "event.voided" for item in controls):
            state = "Voided or superseded; inspect controls"
        elif controls:
            state = "Corrected or superseded"
        else:
            state = "Not effective"
        return page(
            request,
            "Event detail",
            principal,
            kind="event",
            record=record,
            subjects=subjects,
            relations=relations,
            target=target,
            source=source,
            warnings=warnings,
            state=state,
        )

    @router.get("/incidents", response_class=HTMLResponse)
    def incidents(request: Request, q: str = "") -> HTMLResponse:
        principal, denial = access(request, "admin.incident.view")
        if denial:
            return denial
        assert principal is not None
        value = q.strip()[:120]
        results = repository.search(value) if value else {}
        resolved = repository.incident_identity(value) if value else None
        bundle: dict[str, object] = {}
        if resolved:
            subject_kind, record = resolved
            bundle = {"subject_kind": subject_kind, "record": record}
            if subject_kind == "account":
                bundle["memberships"] = repository.memberships(record["user_id"])
                bundle["events"] = repository.events(record["user_id"], "actor_user_id", 1)[:20]
            elif subject_kind == "household":
                bundle["household"] = repository.household_bundle(record["household_id"])
            elif subject_kind == "animal":
                household_id = UUID(record["household_id"])
                animal_id = UUID(record["animal_id"])
                bundle["household"] = repository.household(record["household_id"])
                bundle["members"] = repository.household_bundle(record["household_id"])["members"]
                bundle["history"] = present_effective_care_events(
                    animals.effective_history(household_id, animal_id)
                )[:100]
                bundle["events"] = repository.subject_events(
                    record["household_id"], "animal", record["animal_id"]
                )
                bundle["inventory_links"] = repository.animal_inventory_links(record["animal_id"])
            elif subject_kind in {"enclosure", "inventory"}:
                bundle["household"] = repository.household(record["household_id"])
                bundle["events"] = repository.subject_events(
                    record["household_id"],
                    "enclosure" if subject_kind == "enclosure" else "inventory_item",
                    record["enclosure_id"] if subject_kind == "enclosure" else record["item_id"],
                )
            elif subject_kind in {"event", "correlation"}:
                bundle["events"] = repository.events(record["correlation_id"], "correlation_id", 1)[
                    :30
                ]
        return page(
            request,
            "Incident explorer",
            principal,
            kind="incidents",
            q=value,
            search=results,
            incident=bundle,
        )

    @router.get("/system", response_class=HTMLResponse)
    def system(request: Request) -> HTMLResponse:
        principal, denial = access(request, "admin.system.view")
        if denial:
            return denial
        assert principal is not None
        return page(
            request,
            "System health",
            principal,
            kind="system",
            summary=repository.overview(),
            system=repository.system(),
            storage=repository.storage_health(attachment_root, reference_root),
            environment=environment,
            version=version,
            checked_at=datetime.now(UTC).isoformat(),
        )

    @router.get("/audit", response_class=HTMLResponse)
    def audit(
        request: Request,
        operator: str = "",
        action: str = "",
        target_type: str = "",
        target_id: str = "",
        since: str = "",
        until: str = "",
        p: int = 1,
    ) -> HTMLResponse:
        principal, denial = access(request, "admin.audit.view")
        if denial:
            return denial
        assert principal is not None
        p = max(1, min(p, 10000))
        rows, more = pagination(
            repository.audit_rows(
                operator[:36],
                action[:100],
                target_type[:64],
                target_id[:36],
                since[:32],
                until[:32],
                p,
            )
        )
        return page(
            request,
            "Admin audit",
            principal,
            kind="audit",
            rows=rows,
            more=more,
            p=p,
            operator_filter=operator[:36],
            action=action[:100],
            target_type=target_type[:64],
            target_id=target_id[:36],
            since=since[:32],
            until=until[:32],
        )

    @router.get("/support-notes", response_class=HTMLResponse)
    def notes(request: Request) -> HTMLResponse:
        principal, denial = access(request, "admin.support_notes.view")
        if denial:
            return denial
        assert principal is not None
        return page(request, "Support notes", principal, kind="notes")

    return router
