"""Server-rendered identity and household browser experience."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from calendar import Calendar
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from snaketracker.application.analytics import (
    AnalyticsNotAvailableError,
    AnimalAnalytics,
    AnimalAnalyticsService,
)
from snaketracker.application.animals import (
    CONTROLLABLE_ANIMAL_EVENT_TYPES,
    AnimalService,
    AnimalValidationError,
    AssignEnclosureCommand,
    ChangeAnimalStatusCommand,
    CorrectFeedingCommand,
    CorrectLengthCommand,
    CorrectMoltCommand,
    CorrectShedCommand,
    CorrectWeightCommand,
    RecordBathCommand,
    RecordFeedingCommand,
    RecordLengthCommand,
    RecordMoltCommand,
    RecordPremoltCommand,
    RecordShedCommand,
    RecordWeightCommand,
    RegisterAnimalCommand,
    ReinstateAnimalEventCommand,
    UpdateAnimalProfileCommand,
    VoidAnimalEventCommand,
)
from snaketracker.application.attachments import (
    MAX_PROFILE_PHOTO_BYTES,
    AttachmentService,
    AttachmentValidationError,
    FinalizeProfilePhotoCommand,
    SelectProfilePhotoCommand,
    StageProfilePhotoCommand,
)
from snaketracker.application.backups import (
    BackupService,
    BackupValidationError,
    ConfigureBackupScheduleCommand,
    RequestBackupCommand,
)
from snaketracker.application.dashboard import DashboardStatisticsService
from snaketracker.application.enclosures import (
    ChangeEnclosureStatusCommand,
    EnclosureService,
    EnclosureValidationError,
    RecordCleaningCommand,
    RecordMistingCommand,
    RecordWaterChangeCommand,
    RegisterEnclosureCommand,
    UpdateEnclosureProfileCommand,
)
from snaketracker.application.expenses import (
    CorrectExpenseCommand,
    ExpenseAuthorizationError,
    ExpenseService,
    ExpenseValidationError,
    RecordExpenseCommand,
    VoidExpenseCommand,
)
from snaketracker.application.household_bootstrap import (
    AccountRegistrationCommand,
    AccountRegistrationConflictError,
    AccountRegistrationService,
    AlreadyBootstrappedError,
    BootstrapCommand,
    BootstrapConflictError,
    BootstrapValidationError,
    HouseholdBootstrapService,
)
from snaketracker.application.identity import (
    AuthenticationError,
    IdentityService,
    InvalidPasswordResetError,
    LoginBlockedError,
    PasswordResetValidationError,
    Principal,
)
from snaketracker.application.inventory import (
    AdjustStockCommand,
    ArchiveInventoryItemCommand,
    InventoryService,
    InventoryValidationError,
    ReceiveStockCommand,
    RegisterInventoryItemCommand,
    RestoreInventoryItemCommand,
    UpdateInventoryItemCommand,
)
from snaketracker.application.reminders import (
    CreateReminderRuleCommand,
    DisableReminderRuleCommand,
    ReminderFactService,
    ReminderProjection,
    ReminderRuleCurrent,
    ReminderRuleService,
    ReminderValidationError,
    SaveSubjectScheduleCommand,
)
from snaketracker.application.reports import KeeperReport, ReportService
from snaketracker.application.search import (
    SearchResult,
    SearchService,
    SearchUnavailableError,
    SearchValidationError,
)
from snaketracker.application.suggestion_policy import CareWindowEstimate
from snaketracker.domains.animals.capabilities import (
    AnimalCapability,
    animal_capability_registry,
)
from snaketracker.domains.animals.contracts import ANIMAL_STATUSES
from snaketracker.domains.enclosures.contracts import ENCLOSURE_STATUSES
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.registry import production_event_registry
from snaketracker.platform.events.store import ExpectedVersionConflictError
from snaketracker.platform.events.validation import household_local_to_utc
from snaketracker.platform.jobs.models import JobRecord
from snaketracker.platform.notifications.service import NotificationIntentService
from snaketracker.presentation.animal_care_views import (
    CareEventView,
    present_care_events,
    present_effective_care_events,
)

SESSION_COOKIE = "snaketracker_session"
CSRF_COOKIE = "snaketracker_csrf"
PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")

CARE_FORM_DETAILS: dict[str, tuple[str, str, str]] = {
    "feeding": ("Record feeding", "Add the offered prey and observed outcome.", "feedings"),
    "weight": ("Record weight", "Add the animal's measured weight in grams.", "weights"),
    "length": ("Record length", "Add the animal's measured length in millimetres.", "lengths"),
    "shed": ("Record shed", "Add the observed shed state or completed result.", "sheds"),
    "bath": ("Record bath", "Add a completed bath or soak.", "baths"),
    "molt": ("Record molt", "Add the observed molt result.", "molts"),
    "premolt": (
        "Premolt observation",
        "Record or clear the observed premolt state.",
        "premolt-observations",
    ),
    "misting": (
        "Record misting",
        "Add watering or misting care for the current enclosure.",
        "mistings",
    ),
}

CARE_SCHEDULE_CAPABILITIES: dict[str, tuple[str, str, str]] = {
    "feeding": ("Feeding", "animal", "last accepted feeding"),
    "weight": ("Weight check", "animal", "last weight"),
    "length": ("Length check", "animal", "last length"),
    "bath": ("Bath / soak", "animal", "last bath"),
    "molt": ("Molt check", "animal", "last molt"),
    "misting": ("Misting / watering", "enclosure", "last misting"),
    "cleaning": ("Enclosure cleaning", "enclosure", "last qualifying cleaning"),
    "water_change": ("Water change", "enclosure", "last water change"),
}

RECENT_CARE_EVENT_TYPES = frozenset(
    {
        "animal.feeding_recorded",
        "animal.feeding_corrected",
        "animal.weight_recorded",
        "animal.weight_corrected",
        "animal.length_recorded",
        "animal.length_corrected",
        "animal.shed_recorded",
        "animal.shed_corrected",
        "animal.bath_recorded",
        "animal.molt_recorded",
        "animal.molt_corrected",
        "animal.premolt_observed",
        "animal.enclosure_assigned",
        "enclosure.misting_recorded",
        "enclosure.cleaning_recorded",
        "enclosure.water_change_recorded",
    }
)


def _recent_care_views(
    events: tuple[DomainEvent, ...], *, enclosure_names: Mapping[UUID, str]
) -> tuple[CareEventView, ...]:
    return present_effective_care_events(
        tuple(event for event in events if event.event_type in RECENT_CARE_EVENT_TYPES),
        enclosure_names=enclosure_names,
    )


class FormValidationError(ValueError):
    """A browser form value cannot be converted to an owned command input."""


class JobReadRepository(Protocol):
    def list_for(self, household_id: UUID) -> tuple[JobRecord, ...]: ...


@dataclass(frozen=True, slots=True)
class AnalyticsInsightView:
    """Capability-aware keeper copy around a deterministic estimate."""

    kind: str
    label: str
    progress_label: str
    observed_count: int
    required_count: int
    estimate: CareWindowEstimate | None


def _analytics_insights(analytics: AnimalAnalytics) -> tuple[AnalyticsInsightView, ...]:
    estimates = {item.kind: item for item in analytics.suggestions}
    accepted_feedings = sum(1 for item in analytics.feedings if item.outcome == "accepted")
    care_actions = frozenset(analytics.animal.care_action_keys)
    insights = []
    if "feeding" in care_actions:
        insights.append(
            AnalyticsInsightView(
                kind="feeding",
                label="Feeding",
                progress_label="accepted feedings",
                observed_count=accepted_feedings,
                required_count=6,
                estimate=estimates.get("feeding"),
            )
        )
    for kind, label, plural in (
        ("shed", "Shed", "completed sheds"),
        ("molt", "Molt", "completed molts"),
    ):
        if kind in care_actions:
            insights.append(
                AnalyticsInsightView(
                    kind=kind,
                    label=label,
                    progress_label=plural,
                    observed_count=sum(1 for item in analytics.husbandry if item.kind == kind),
                    required_count=5,
                    estimate=estimates.get(kind),
                )
            )
    return tuple(insights)


def _form_datetime(value: object, household_timezone: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise FormValidationError("Enter a valid date and time.") from error
    if parsed.tzinfo is None:
        return household_local_to_utc(parsed, household_timezone)
    return parsed.astimezone(UTC)


def _required_int(value: object, label: str) -> int:
    try:
        return int(str(value))
    except ValueError as error:
        raise FormValidationError(f"Enter a whole-number {label}.") from error


def _optional_int(value: object, label: str) -> int | None:
    normalized = str(value).strip()
    return None if not normalized else _required_int(normalized, label)


def _money_minor(value: object) -> int:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as error:
        raise FormValidationError("Enter a valid monetary amount.") from error
    minor = int(amount * 100)
    if minor < 1:
        raise FormValidationError("Expense amount must be positive.")
    return minor


def _friendly_money(amount_minor: int, currency: str) -> str:
    amount = amount_minor / 100
    return f"${amount:,.2f}" if currency.upper() == "USD" else f"{currency.upper()} {amount:,.2f}"


def _friendly_expense_total(expenses: tuple[Any, ...]) -> str:
    totals: dict[str, int] = {}
    for expense in expenses:
        totals[expense.currency] = totals.get(expense.currency, 0) + expense.amount_minor
    if not totals:
        return "$0.00"
    return " + ".join(
        _friendly_money(total, currency) for currency, total in sorted(totals.items())
    )


def _friendly_report_value(column: str, value: str) -> str:
    if column == "Occurred":
        try:
            return datetime.fromisoformat(value).strftime("%b %-d, %Y · %-I:%M %p")
        except ValueError:
            return value
    return value.replace("_", " ").title() if column in {"Type", "Status", "Record"} else value


def _report_display_rows(report: KeeperReport) -> tuple[tuple[dict[str, str], ...], ...]:
    currency_index = report.columns.index("Currency") if "Currency" in report.columns else None
    display_rows = []
    for row in report.rows:
        currency = row.values[currency_index] if currency_index is not None else ""
        cells = []
        for column, value in zip(report.columns, row.values, strict=True):
            if column == "Amount" and currency:
                with suppress(InvalidOperation, ValueError):
                    value = _friendly_money(int(Decimal(value) * 100), currency)
            cells.append({"label": column, "value": _friendly_report_value(column, value)})
        display_rows.append(tuple(cells))
    return tuple(display_rows)


def _inventory_reference(form: Any) -> tuple[UUID | None, int | None]:
    raw = str(form.get("inventory_item_id", "")).strip()
    if not raw:
        return None, None
    if ":" in raw:
        item_value, version_value = raw.rsplit(":", 1)
        return UUID(item_value), _required_int(version_value, "inventory stream version")
    return UUID(raw), _optional_int(
        form.get("inventory_expected_stream_version", ""), "inventory stream version"
    )


def _form_bool(value: object, label: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise FormValidationError(f"Choose a valid {label} value.")


def _form_idempotency_key(form: Any) -> str:
    return str(form.get("idempotency_key") or form["csrf_token"])


def _form_values(form: Any) -> dict[str, str]:
    return {str(key): str(value) for key, value in form.items()}


def _care_return_context(value: object) -> str:
    return str(value) if str(value) in {"today", "care"} else "animal"


def _care_return_location(animal_id: str, value: object) -> str:
    context = _care_return_context(value)
    if context == "today":
        return "/home"
    if context == "care":
        return f"/animals/{animal_id}/care"
    return f"/animals/{animal_id}"


def _timeline_action_ids(events: tuple[DomainEvent, ...]) -> dict[str, frozenset[UUID]]:
    active_voids: set[UUID] = set()
    for event in events:
        if isinstance(event.payload, EventVoidedV1):
            active_voids.add(event.payload.target_event_id)
        elif isinstance(event.payload, EventReinstatedV1):
            active_voids.discard(event.payload.target_event_id)
    correctable: set[UUID] = set()
    voidable: set[UUID] = set()
    reinstatable: set[UUID] = set()
    for event in events:
        capabilities = production_event_registry.registration(
            event.event_type, event.schema_version
        ).correction
        if capabilities.correctable:
            correctable.add(event.event_id)
        controls_supported = event.event_type in CONTROLLABLE_ANIMAL_EVENT_TYPES
        if capabilities.voidable and controls_supported and event.event_id not in active_voids:
            voidable.add(event.event_id)
        if capabilities.reinstatable and controls_supported and event.event_id in active_voids:
            reinstatable.add(event.event_id)
    return {
        "correctable_event_ids": frozenset(correctable),
        "voidable_event_ids": frozenset(voidable),
        "reinstatable_event_ids": frozenset(reinstatable),
    }


def _timeline_context(
    animal_service: AnimalService,
    enclosure_service: EnclosureService,
    household_id: UUID,
    animal_id: UUID,
) -> dict[str, Any]:
    audit_events = animal_service.audit_history(household_id, animal_id)
    enclosure_names = {
        enclosure.enclosure_id: enclosure.name
        for enclosure in enclosure_service.list_profiles(household_id)
    }
    return {
        "events": present_effective_care_events(
            animal_service.effective_history(household_id, animal_id),
            enclosure_names=enclosure_names,
        ),
        "audit_events": present_care_events(audit_events, enclosure_names=enclosure_names),
        "errors": {},
        **_timeline_action_ids(audit_events),
    }


def _animal_event(
    animal_service: AnimalService, household_id: UUID, animal_id: UUID, event_id: UUID
) -> DomainEvent | None:
    return next(
        (
            event
            for event in animal_service.audit_history(household_id, animal_id)
            if event.event_id == event_id
        ),
        None,
    )


def _correct_animal_event_from_form(
    animal_service: AnimalService,
    principal: Principal,
    animal_id: UUID,
    target: DomainEvent,
    form: Any,
) -> None:
    idempotency_key = _form_idempotency_key(form)
    occurred_at = _form_datetime(form.get("occurred_at", ""), principal.household_timezone)
    notes = str(form.get("notes", ""))
    if target.event_type == "animal.feeding_recorded":
        animal_service.correct_feeding(
            CorrectFeedingCommand(
                household_id=principal.household_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                animal_id=animal_id,
                target_event_id=target.event_id,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                notes=notes,
                prey_type=str(form.get("prey_type", "")),
                prey_size=str(form.get("prey_size", "")),
                prey_weight_grams=_optional_int(form.get("prey_weight_grams", ""), "prey weight"),
                preparation_method=str(form.get("preparation_method", "")),
                quantity=_required_int(form.get("quantity", ""), "quantity"),
                outcome=str(form.get("outcome", "")),
            )
        )
        return
    if target.event_type == "animal.weight_recorded":
        animal_service.correct_weight(
            CorrectWeightCommand(
                household_id=principal.household_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                animal_id=animal_id,
                target_event_id=target.event_id,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                notes=notes,
                weight_grams=_required_int(form.get("weight_grams", ""), "weight"),
            )
        )
        return
    if target.event_type == "animal.length_recorded":
        animal_service.correct_length(
            CorrectLengthCommand(
                household_id=principal.household_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                animal_id=animal_id,
                target_event_id=target.event_id,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                notes=notes,
                length_mm=_required_int(form.get("length_mm", ""), "length"),
            )
        )
        return
    if target.event_type == "animal.shed_recorded":
        animal_service.correct_shed(
            CorrectShedCommand(
                household_id=principal.household_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                animal_id=animal_id,
                target_event_id=target.event_id,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                notes=notes,
                blue_state=_form_bool(form.get("blue_state", ""), "blue-state"),
                completed=_form_bool(form.get("completed", ""), "completion"),
                result=str(form.get("result", "")).strip() or None,
            )
        )
        return
    if target.event_type == "animal.molt_recorded":
        animal_service.correct_molt(
            CorrectMoltCommand(
                household_id=principal.household_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                animal_id=animal_id,
                target_event_id=target.event_id,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                result=str(form.get("result", "")),
                observation=notes,
            )
        )
        return
    raise FormValidationError("This care record cannot be corrected.")


def _client_context(request: Request) -> tuple[str | None, str | None]:
    client_ip = request.client.host if request.client else None
    return client_ip, request.headers.get("user-agent")


def _set_cookie(
    response: RedirectResponse | HTMLResponse, name: str, value: str, secure: bool
) -> None:
    response.set_cookie(
        name,
        value,
        secure=secure,
        httponly=True,
        samesite="strict",
        path="/",
    )


def _new_form_response(
    request: Request,
    template: str,
    *,
    secure_cookie: bool,
    status_code: int = 200,
    context: dict[str, Any] | None = None,
) -> HTMLResponse:
    csrf_token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        request,
        template,
        {
            "csrf_token": csrf_token,
            "command_id": str(uuid4()),
            "errors": {},
            "values": {},
            **(context or {}),
        },
        status_code=status_code,
    )
    _set_cookie(response, CSRF_COOKIE, csrf_token, secure_cookie)
    return response


def _access_denied(request: Request, title: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        {"title": title, "message": "Your current household role cannot use this feature."},
        status_code=403,
    )


def _not_found(request: Request, title: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        {"title": title, "message": "Return to your household workspace and try again."},
        status_code=404,
    )


def _preauth_csrf_valid(request: Request, submitted: str) -> bool:
    cookie = request.cookies.get(CSRF_COOKIE)
    return cookie is not None and hmac.compare_digest(cookie, submitted)


def _form_request_valid(request: Request, expected_origin: str | None) -> bool:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    }:
        return False
    origin = request.headers.get("origin")
    allowed_origin = (expected_origin or str(request.base_url)).rstrip("/")
    return origin is None or hmac.compare_digest(origin.rstrip("/"), allowed_origin)


def create_web_router(
    *,
    bootstrap_service: HouseholdBootstrapService,
    account_registration_service: AccountRegistrationService,
    identity_service: IdentityService,
    animal_service: AnimalService,
    attachment_service: AttachmentService,
    backup_service: BackupService,
    enclosure_service: EnclosureService,
    inventory_service: InventoryService,
    expense_service: ExpenseService,
    analytics_service: AnimalAnalyticsService,
    report_service: ReportService,
    dashboard_statistics_service: DashboardStatisticsService,
    reminder_rule_service: ReminderRuleService,
    reminder_fact_service: ReminderFactService,
    reminder_projection: ReminderProjection,
    notification_intent_service: NotificationIntentService,
    job_repository: JobReadRepository,
    search_service: SearchService,
    projection_catch_up: Callable[[], object] | None,
    is_bootstrapped: Callable[[], bool],
    secure_cookie: bool,
    expected_origin: str | None = None,
) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    def principal_for(request: Request, *, audit_denial: bool = False) -> Principal | None:
        token = request.cookies.get(SESSION_COOKIE)
        if token is None:
            if audit_denial:
                client_ip, user_agent = _client_context(request)
                identity_service.audit_access_denied(
                    correlation_id=uuid4(), client_ip=client_ip, user_agent=user_agent
                )
            return None
        try:
            return identity_service.authenticate(token)
        except AuthenticationError:
            if audit_denial:
                client_ip, user_agent = _client_context(request)
                identity_service.audit_access_denied(
                    correlation_id=uuid4(), client_ip=client_ip, user_agent=user_agent
                )
            return None

    def protected_page(
        request: Request,
        template: str,
        principal: Principal,
        *,
        status_code: int = 200,
        context: dict[str, Any] | None = None,
    ) -> HTMLResponse:
        csrf_token = request.cookies.get(CSRF_COOKIE)
        issued = None
        if csrf_token is None:
            token = request.cookies.get(SESSION_COOKIE)
            if token is None:
                raise RuntimeError("Authenticated request is missing its session token.")
            client_ip, user_agent = _client_context(request)
            issued = identity_service.rotate_session(
                token,
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=uuid4(),
            )
            csrf_token = issued.csrf_token
        response = templates.TemplateResponse(
            request,
            template,
            {
                "principal": principal,
                "household_zone": ZoneInfo(principal.household_timezone),
                "csrf_token": csrf_token,
                "command_id": str(uuid4()),
                **(context or {}),
            },
            status_code=status_code,
        )
        if issued is not None:
            _set_cookie(response, SESSION_COOKIE, issued.token, secure_cookie)
            _set_cookie(response, CSRF_COOKIE, issued.csrf_token, secure_cookie)
        return response

    async def protected_form(
        request: Request,
        *,
        max_files: int = 1000,
        max_fields: int = 1000,
        max_part_size: int = 1024 * 1024,
        parse_error_message: str = "The submitted form could not be processed. Try again.",
    ) -> tuple[Principal | None, Any | None, Response | None]:
        if not _form_request_valid(request, expected_origin):
            return (
                None,
                None,
                templates.TemplateResponse(
                    request,
                    "error.html",
                    {
                        "title": "Request could not be verified",
                        "message": "Return to the form and try again.",
                    },
                    status_code=403,
                ),
            )
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return None, None, RedirectResponse("/login", status_code=303)
        try:
            form = await request.form(
                max_files=max_files,
                max_fields=max_fields,
                max_part_size=max_part_size,
            )
        except StarletteHTTPException:
            return (
                None,
                None,
                templates.TemplateResponse(
                    request,
                    "error.html",
                    {
                        "title": "Form could not be processed",
                        "message": parse_error_message,
                    },
                    status_code=422,
                ),
            )
        token = request.cookies.get(SESSION_COOKIE)
        submitted = str(form.get("csrf_token", ""))
        if token is None or not identity_service.verify_csrf(token, submitted):
            return (
                None,
                None,
                templates.TemplateResponse(
                    request,
                    "error.html",
                    {
                        "title": "Request could not be verified",
                        "message": "Refresh the form and try again.",
                    },
                    status_code=403,
                ),
            )
        return principal, form, None

    def animal_experience_context(principal: Principal, animal: Any) -> dict[str, Any]:
        """Compose the shared, capability-driven animal experience view model."""
        now = datetime.now(UTC)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        animals = animal_service.list_profiles(principal.household_id)
        current_enclosure = next(
            (
                enclosure
                for enclosure in enclosures
                if enclosure.enclosure_id == animal.current_enclosure_id
            ),
            None,
        )
        enclosure_names = {enclosure.enclosure_id: enclosure.name for enclosure in enclosures}
        recent_events = _recent_care_views(
            animal_service.effective_history(principal.household_id, animal.animal_id),
            enclosure_names=enclosure_names,
        )
        related_subjects = {("animal", animal.animal_id)}
        if current_enclosure is not None:
            related_subjects.add(("enclosure", current_enclosure.enclosure_id))
        related_facts = tuple(
            fact
            for fact in reminder_projection.facts_for(principal.household_id)
            if (fact.subject_type, fact.subject_id) in related_subjects
            and fact.reminder_type in animal.reminder_kinds
        )
        agenda = _agenda_rows(
            tuple(sorted(related_facts, key=lambda fact: fact.due_at)),
            animals=animals,
            enclosures=enclosures,
            timezone=ZoneInfo(principal.household_timezone),
            now=now,
            return_context="animal",
        )
        next_care = next(
            (row for status in ("overdue", "due_today", "upcoming") for row in agenda[status]),
            None,
        )

        def latest(event_types: frozenset[str]) -> CareEventView | None:
            return next(
                (item for item in recent_events if item.event.event_type in event_types), None
            )

        overview_care_facts = tuple(
            item
            for item in (
                {
                    "label": "Latest weight",
                    "event": latest(
                        frozenset({"animal.weight_recorded", "animal.weight_corrected"})
                    ),
                },
                {
                    "label": "Latest length",
                    "event": latest(
                        frozenset({"animal.length_recorded", "animal.length_corrected"})
                    ),
                },
                {
                    "label": "Latest feeding",
                    "event": latest(
                        frozenset({"animal.feeding_recorded", "animal.feeding_corrected"})
                    ),
                }
                if "feeding" in animal.care_action_keys
                else None,
                {
                    "label": "Latest shed",
                    "event": latest(frozenset({"animal.shed_recorded", "animal.shed_corrected"})),
                }
                if "shed" in animal.care_action_keys
                else None,
                {
                    "label": "Latest molt",
                    "event": latest(frozenset({"animal.molt_recorded", "animal.molt_corrected"})),
                }
                if "molt" in animal.care_action_keys
                else None,
            )
            if item is not None
        )
        return {
            "animal": animal,
            "enclosures": enclosures,
            "current_enclosure": current_enclosure,
            "recent_events": recent_events[:6],
            "care_actions": _care_action_rows(animal),
            "premolt_status": _premolt_status(animal, animal_service),
            "animal_statuses": tuple(sorted(ANIMAL_STATUSES)),
            "care_schedules": _care_schedule_rows(
                principal.household_id,
                animal,
                current_enclosure,
                reminder_projection,
                principal.household_timezone,
                related_facts,
                now,
            ),
            "next_care": next_care,
            "overview_care_facts": overview_care_facts,
        }

    def animal_management_response(
        request: Request,
        principal: Principal,
        animal_id: str,
        manage_kind: str,
        *,
        status_code: int = 200,
        error: str | None = None,
    ) -> Response:
        try:
            animal = animal_service.profile_for(principal.household_id, UUID(animal_id))
        except ValueError:
            animal = None
        if animal is None:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=404,
                context={
                    "title": "Animal not found",
                    "message": "Return to your animal list and try again.",
                },
            )
        return protected_page(
            request,
            "animal_manage.html",
            principal,
            status_code=status_code,
            context={
                **animal_experience_context(principal, animal),
                "manage_kind": manage_kind,
                "errors": {"form": error} if error else {},
            },
        )

    def onboarding_context(principal: Principal) -> dict[str, Any]:
        animals = animal_service.list_profiles(principal.household_id)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        rules = reminder_projection.rules_for(principal.household_id)
        first_animal = animals[0] if animals else None
        has_assigned_enclosure = any(animal.current_enclosure_id is not None for animal in animals)
        has_schedule = any(rule.enabled for rule in rules)
        steps = (
            {
                "label": "Collection created",
                "description": principal.household_name,
                "complete": True,
            },
            {
                "label": "Add your first animal",
                "description": "Create the profile you will care for.",
                "complete": bool(animals),
            },
            {
                "label": "Add an enclosure",
                "description": "Record the habitat before assigning it.",
                "complete": bool(enclosures),
            },
            {
                "label": "Assign an enclosure",
                "description": "Connect an animal to its current habitat.",
                "complete": has_assigned_enclosure,
            },
            {
                "label": "Set a care schedule",
                "description": "Choose an interval that fits your own care plan.",
                "complete": has_schedule,
            },
        )
        if not animals:
            next_url, next_label = "/animals/new", "Add your first animal"
        elif not enclosures:
            next_url, next_label = "/enclosures/new", "Add an enclosure"
        elif not has_assigned_enclosure and first_animal is not None:
            next_url = f"/animals/{first_animal.animal_id}/enclosure"
            next_label = f"Assign {first_animal.name} an enclosure"
        elif not has_schedule and first_animal is not None:
            next_url = f"/animals/{first_animal.animal_id}/care"
            next_label = f"Set {first_animal.name}'s care schedule"
        else:
            next_url, next_label = "/home", "Go to Today"
        return {
            "onboarding_steps": steps,
            "onboarding_complete": all(step["complete"] for step in steps),
            "onboarding_next_url": next_url,
            "onboarding_next_label": next_label,
        }

    @router.get("/")
    async def index(request: Request) -> RedirectResponse:
        if not is_bootstrapped():
            return RedirectResponse("/setup", status_code=303)
        return RedirectResponse("/home" if principal_for(request) else "/login", status_code=303)

    @router.get("/setup", response_class=HTMLResponse)
    async def setup_page(request: Request) -> Response:
        if is_bootstrapped():
            return RedirectResponse(
                "/home" if principal_for(request) else "/login", status_code=303
            )
        return _new_form_response(request, "setup.html", secure_cookie=secure_cookie)

    @router.post("/setup", response_class=HTMLResponse)
    async def setup_submit(request: Request) -> Response:
        if not _form_request_valid(request, expected_origin):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Refresh the page and try again.",
                },
                status_code=403,
            )
        form = await request.form()
        submitted_csrf = str(form.get("csrf_token", ""))
        if not _preauth_csrf_valid(request, submitted_csrf):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Refresh the page and try again.",
                },
                status_code=403,
            )
        values = {
            name: str(form.get(name, "")).strip()
            for name in ("household_name", "timezone", "display_name", "email")
        }
        password = str(form.get("password", ""))
        confirmation = str(form.get("password_confirmation", ""))
        errors: dict[str, str] = {}
        if password != confirmation:
            errors["password_confirmation"] = "Passwords do not match."
        try:
            ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError:
            errors["timezone"] = "Enter a valid IANA timezone."
        if errors:
            return _new_form_response(
                request,
                "setup.html",
                secure_cookie=secure_cookie,
                status_code=422,
                context={"errors": errors, "values": values},
            )
        try:
            result = bootstrap_service.bootstrap(
                BootstrapCommand(
                    household_name=values["household_name"],
                    timezone=values["timezone"],
                    owner_email=values["email"],
                    owner_display_name=values["display_name"],
                    password=password,
                    idempotency_key=submitted_csrf,
                    correlation_id=uuid4(),
                )
            )
        except BootstrapValidationError as error:
            return _new_form_response(
                request,
                "setup.html",
                secure_cookie=secure_cookie,
                status_code=422,
                context={"errors": {"form": str(error)}, "values": values},
            )
        except (AlreadyBootstrappedError, BootstrapConflictError):
            return RedirectResponse("/login", status_code=303)
        client_ip, user_agent = _client_context(request)
        issued = identity_service.create_session_for_user(
            result.user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            correlation_id=uuid4(),
        )
        response = RedirectResponse("/home", status_code=303)
        _set_cookie(response, SESSION_COOKIE, issued.token, secure_cookie)
        _set_cookie(response, CSRF_COOKIE, issued.csrf_token, secure_cookie)
        return response

    @router.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> Response:
        if not is_bootstrapped():
            return RedirectResponse("/setup", status_code=303)
        if principal_for(request):
            return RedirectResponse("/home", status_code=303)
        return _new_form_response(
            request,
            "login.html",
            secure_cookie=secure_cookie,
            context={"password_reset_complete": request.query_params.get("reset") == "complete"},
        )

    @router.get("/forgot-password", response_class=HTMLResponse)
    async def forgot_password_page(request: Request) -> Response:
        if not is_bootstrapped():
            return RedirectResponse("/setup", status_code=303)
        response = _new_form_response(request, "forgot_password.html", secure_cookie=secure_cookie)
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/forgot-password", response_class=HTMLResponse)
    async def forgot_password_submit(request: Request) -> Response:
        if not is_bootstrapped():
            return RedirectResponse("/setup", status_code=303)
        if not _form_request_valid(request, expected_origin):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Refresh the password recovery page and try again.",
                },
                status_code=403,
            )
        form = await request.form()
        if not _preauth_csrf_valid(request, str(form.get("csrf_token", ""))):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Refresh the password recovery page and try again.",
                },
                status_code=403,
            )
        client_ip, user_agent = _client_context(request)
        identity_service.request_password_reset(
            str(form.get("email", "")),
            client_ip=client_ip,
            user_agent=user_agent,
            correlation_id=uuid4(),
        )
        response = RedirectResponse("/forgot-password/sent", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.get("/forgot-password/sent", response_class=HTMLResponse)
    async def forgot_password_sent(request: Request) -> Response:
        response = templates.TemplateResponse(request, "password_reset_sent.html", {})
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.get("/reset-password", response_class=HTMLResponse)
    async def reset_password_page(request: Request) -> Response:
        if not is_bootstrapped():
            return RedirectResponse("/setup", status_code=303)
        response = _new_form_response(
            request,
            "reset_password.html",
            secure_cookie=secure_cookie,
            context={"reset_token": ""},
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/reset-password", response_class=HTMLResponse)
    async def reset_password_submit(request: Request) -> Response:
        if not _form_request_valid(request, expected_origin):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Open the reset link again and try once more.",
                },
                status_code=403,
            )
        form = await request.form()
        if not _preauth_csrf_valid(request, str(form.get("csrf_token", ""))):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Open the reset link again and try once more.",
                },
                status_code=403,
            )
        token = str(form.get("reset_token", ""))
        client_ip, user_agent = _client_context(request)
        try:
            identity_service.complete_password_reset(
                token,
                str(form.get("password", "")),
                str(form.get("password_confirmation", "")),
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=uuid4(),
            )
        except PasswordResetValidationError as error:
            response = _new_form_response(
                request,
                "reset_password.html",
                secure_cookie=secure_cookie,
                status_code=422,
                context={"error": str(error), "reset_token": token},
            )
            response.headers["Cache-Control"] = "no-store"
            return response
        except InvalidPasswordResetError:
            response = templates.TemplateResponse(
                request, "password_reset_invalid.html", {}, status_code=400
            )
            response.headers["Cache-Control"] = "no-store"
            return response
        redirect = RedirectResponse("/login?reset=complete", status_code=303)
        redirect.delete_cookie(SESSION_COOKIE, path="/")
        redirect.delete_cookie(CSRF_COOKIE, path="/")
        redirect.headers["Cache-Control"] = "no-store"
        return redirect

    @router.get("/register", response_class=HTMLResponse)
    async def registration_page(request: Request) -> Response:
        if not is_bootstrapped():
            return RedirectResponse("/setup", status_code=303)
        if principal_for(request):
            return RedirectResponse("/home", status_code=303)
        return _new_form_response(request, "register.html", secure_cookie=secure_cookie)

    @router.post("/register", response_class=HTMLResponse)
    async def registration_submit(request: Request) -> Response:
        if not is_bootstrapped():
            return RedirectResponse("/setup", status_code=303)
        if not _form_request_valid(request, expected_origin):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Refresh the registration page and try again.",
                },
                status_code=403,
            )
        form = await request.form()
        submitted_csrf = str(form.get("csrf_token", ""))
        if not _preauth_csrf_valid(request, submitted_csrf):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Refresh the registration page and try again.",
                },
                status_code=403,
            )
        values = {
            name: str(form.get(name, "")).strip()
            for name in ("collection_name", "timezone", "display_name", "email")
        }
        command_id = str(form.get("idempotency_key", "")).strip()
        password = str(form.get("password", ""))
        confirmation = str(form.get("password_confirmation", ""))
        client_ip, user_agent = _client_context(request)
        correlation_id = uuid4()
        if identity_service.registration_is_blocked(values["email"], client_ip=client_ip):
            return _new_form_response(
                request,
                "register.html",
                secure_cookie=secure_cookie,
                status_code=429,
                context={
                    "errors": {"form": "Too many attempts. Please wait and try again."},
                    "values": values,
                    "command_id": command_id or str(uuid4()),
                },
            )
        errors: dict[str, str] = {}
        if password != confirmation:
            errors["password_confirmation"] = "Passwords do not match."
        try:
            ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError:
            errors["timezone"] = "Enter a valid IANA timezone."
        if errors:
            identity_service.record_registration_failure(
                values["email"],
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=correlation_id,
            )
            return _new_form_response(
                request,
                "register.html",
                secure_cookie=secure_cookie,
                status_code=422,
                context={"errors": errors, "values": values, "command_id": command_id},
            )
        try:
            result = account_registration_service.register(
                AccountRegistrationCommand(
                    collection_name=values["collection_name"],
                    timezone=values["timezone"],
                    email=values["email"],
                    display_name=values["display_name"],
                    password=password,
                    idempotency_key=command_id,
                    correlation_id=correlation_id,
                )
            )
        except BootstrapValidationError as error:
            identity_service.record_registration_failure(
                values["email"],
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=correlation_id,
            )
            return _new_form_response(
                request,
                "register.html",
                secure_cookie=secure_cookie,
                status_code=422,
                context={
                    "errors": {"form": str(error)},
                    "values": values,
                    "command_id": command_id,
                },
            )
        except (AccountRegistrationConflictError, BootstrapConflictError):
            identity_service.record_registration_failure(
                values["email"],
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=correlation_id,
            )
            return _new_form_response(
                request,
                "register.html",
                secure_cookie=secure_cookie,
                status_code=422,
                context={
                    "errors": {
                        "form": "Account could not be created. Review your details or sign in."
                    },
                    "values": values,
                    "command_id": command_id,
                },
            )
        identity_service.clear_registration_failures(values["email"], client_ip=client_ip)
        issued = identity_service.create_session_for_user(
            result.user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            correlation_id=uuid4(),
        )
        response = RedirectResponse("/onboarding", status_code=303)
        _set_cookie(response, SESSION_COOKIE, issued.token, secure_cookie)
        _set_cookie(response, CSRF_COOKIE, issued.csrf_token, secure_cookie)
        return response

    @router.post("/login", response_class=HTMLResponse)
    async def login_submit(request: Request) -> Response:
        if not _form_request_valid(request, expected_origin):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Refresh the login page and try again.",
                },
                status_code=403,
            )
        form = await request.form()
        csrf_token = str(form.get("csrf_token", ""))
        if not _preauth_csrf_valid(request, csrf_token):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Refresh the login page and try again.",
                },
                status_code=403,
            )
        email = str(form.get("email", ""))
        client_ip, user_agent = _client_context(request)
        try:
            issued = identity_service.login(
                email,
                str(form.get("password", "")),
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=uuid4(),
            )
        except LoginBlockedError as error:
            return _new_form_response(
                request,
                "login.html",
                secure_cookie=secure_cookie,
                status_code=429,
                context={"error": str(error), "email": email},
            )
        except AuthenticationError as error:
            return _new_form_response(
                request,
                "login.html",
                secure_cookie=secure_cookie,
                status_code=401,
                context={"error": str(error), "email": email},
            )
        response = RedirectResponse("/home", status_code=303)
        _set_cookie(response, SESSION_COOKIE, issued.token, secure_cookie)
        _set_cookie(response, CSRF_COOKIE, issued.csrf_token, secure_cookie)
        return response

    @router.get("/home", response_class=HTMLResponse)
    async def home(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if projection_catch_up is not None:
            projection_catch_up()
        csrf_token = request.cookies.get(CSRF_COOKIE)
        issued = None
        if csrf_token is None:
            client_ip, user_agent = _client_context(request)
            issued = identity_service.rotate_session(
                request.cookies[SESSION_COOKIE],
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=uuid4(),
            )
            csrf_token = issued.csrf_token
        animals = animal_service.list_profiles(principal.household_id)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        now = datetime.now(UTC)
        household_zone = ZoneInfo(principal.household_timezone)
        reminder_items = reminder_fact_service.agenda_for(principal.household_id, now=now)
        agenda = _agenda_rows(
            reminder_items,
            animals=animals,
            enclosures=enclosures,
            timezone=household_zone,
            now=now,
        )
        try:
            collection_statistics = dashboard_statistics_service.collection(principal.household_id)
        except RuntimeError:
            collection_statistics = None
        response = templates.TemplateResponse(
            request,
            "home.html",
            {
                "principal": principal,
                "household_zone": household_zone,
                "csrf_token": csrf_token,
                "animals": animals,
                "agenda_counts": {key: len(rows) for key, rows in agenda.items()},
                "today_label": now.astimezone(household_zone).strftime("%A, %B %-d"),
                "agenda_groups": (
                    ("overdue", "Overdue", agenda["overdue"]),
                    ("due_today", "Due today", agenda["due_today"]),
                    ("upcoming", "Upcoming", agenda["upcoming"]),
                ),
                "collection_statistics": collection_statistics,
                "onboarding": onboarding_context(principal),
            },
        )
        if issued is not None:
            _set_cookie(response, SESSION_COOKIE, issued.token, secure_cookie)
            _set_cookie(response, CSRF_COOKIE, issued.csrf_token, secure_cookie)
        return response

    @router.get("/onboarding", response_class=HTMLResponse)
    async def onboarding(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return protected_page(
            request,
            "onboarding.html",
            principal,
            context=onboarding_context(principal),
        )

    @router.get("/animals", response_class=HTMLResponse)
    async def animal_list(request: Request, kind: str = "all") -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        animals = animal_service.list_profiles(principal.household_id)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        now = datetime.now(UTC)
        animal_types = {
            "snakes": "snake",
            "spiders": "spider",
            "lizards": "lizard",
            "scorpions": "scorpion",
        }
        selected_kind = kind if kind in {"all", *animal_types} else "all"
        visible_animals = (
            animals
            if selected_kind == "all"
            else tuple(
                animal for animal in animals if animal.animal_type == animal_types[selected_kind]
            )
        )
        reminder_items = reminder_fact_service.agenda_for(principal.household_id, now=now)
        return protected_page(
            request,
            "animal_list.html",
            principal,
            context={
                "animal_rows": _animal_collection_rows(
                    visible_animals,
                    reminder_items,
                    enclosures=enclosures,
                    timezone=ZoneInfo(principal.household_timezone),
                    now=now,
                ),
                "selected_kind": selected_kind,
                "animal_filters": (
                    ("all", "All", len(animals)),
                    *tuple(
                        (
                            key,
                            key.capitalize(),
                            sum(1 for animal in animals if animal.animal_type == value),
                        )
                        for key, value in animal_types.items()
                    ),
                ),
            },
        )

    @router.get("/more", response_class=HTMLResponse)
    async def more(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return protected_page(request, "more.html", principal)

    @router.get("/calendar", response_class=HTMLResponse)
    async def calendar(
        request: Request, view: str = "agenda", month: str = "", selected: str = ""
    ) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        animals = animal_service.list_profiles(principal.household_id)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        now = datetime.now(UTC)
        household_zone = ZoneInfo(principal.household_timezone)
        reminder_items = reminder_fact_service.agenda_for(principal.household_id, now=now)
        agenda = _agenda_rows(
            reminder_items,
            animals=animals,
            enclosures=enclosures,
            timezone=household_zone,
            now=now,
        )
        completed = _completed_care_rows(
            household_id=principal.household_id,
            animals=animals,
            enclosures=enclosures,
            animal_service=animal_service,
            enclosure_service=enclosure_service,
            timezone=household_zone,
        )
        active_view = view if view in {"agenda", "month"} else "agenda"
        return protected_page(
            request,
            "calendar.html",
            principal,
            context={
                "active_view": active_view,
                "calendar": _calendar_view(
                    month_value=month,
                    selected_value=selected,
                    scheduled_rows=tuple(row for rows in agenda.values() for row in rows),
                    completed=completed,
                    timezone=household_zone,
                    now=now,
                ),
                "agenda_groups": (
                    ("overdue", "Overdue", agenda["overdue"]),
                    ("due_today", "Due today", agenda["due_today"]),
                    ("upcoming", "Upcoming", agenda["upcoming"]),
                ),
            },
        )

    @router.get("/quick-log", response_class=HTMLResponse)
    async def quick_log(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        animals = animal_service.list_profiles(principal.household_id)
        type_order = ("snake", "spider", "lizard", "scorpion")
        return protected_page(
            request,
            "quick_log.html",
            principal,
            context={
                "quick_log_groups": tuple(
                    (
                        animal_capability_registry.require(f"{animal_type}.v1").label,
                        tuple(
                            {"animal": animal, "actions": _care_action_rows(animal)}
                            for animal in animals
                            if animal.animal_type == animal_type
                        ),
                    )
                    for animal_type in type_order
                    if any(animal.animal_type == animal_type for animal in animals)
                ),
            },
        )

    @router.get("/search", response_class=HTMLResponse)
    async def search(request: Request, q: str = "") -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        results: tuple[SearchResult, ...] = ()
        error: str | None = None
        unavailable = False
        try:
            results = search_service.search(principal.household_id, principal.capabilities, q)
        except SearchValidationError as caught:
            error = str(caught)
        except SearchUnavailableError:
            unavailable = True
        animals = animal_service.list_profiles(principal.household_id)
        animal_by_route = {f"/animals/{animal.animal_id}": animal for animal in animals}
        result_rows = tuple(
            {
                "result": result,
                "animal": next(
                    (
                        animal
                        for route, animal in animal_by_route.items()
                        if result.route == route or result.route.startswith(f"{route}/")
                    ),
                    None,
                ),
            }
            for result in results
        )
        return protected_page(
            request,
            "search.html",
            principal,
            status_code=422 if error is not None else 200,
            context={
                "query": q,
                "results": result_rows,
                "error": error,
                "search_unavailable": unavailable,
            },
        )

    def report_for(principal: Principal, kind: str) -> KeeperReport | None:
        generated_at = datetime.now(UTC)
        if kind == "collection":
            return report_service.collection(principal.household_id, generated_at=generated_at)
        if kind == "care":
            return report_service.care(principal.household_id, generated_at=generated_at)
        if kind == "expenses" and "expense.view" in principal.capabilities:
            return report_service.expenses(principal.household_id, generated_at=generated_at)
        return None

    @router.get("/reports", response_class=HTMLResponse)
    async def reports(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if projection_catch_up is not None:
            projection_catch_up()
        kinds = [("collection", "Collection"), ("care", "Care history")]
        if "expense.view" in principal.capabilities:
            kinds.append(("expenses", "Expenses"))
        animals = animal_service.list_profiles(principal.household_id)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        expenses = tuple(
            item
            for item in expense_service.list_expenses(principal.household_id)
            if item.status == "active"
        )
        group_counts: dict[str, int] = {}
        for animal in animals:
            group_counts[animal.type_label] = group_counts.get(animal.type_label, 0) + 1
        return protected_page(
            request,
            "reports.html",
            principal,
            context={
                "report": None,
                "report_kinds": kinds,
                "report_summary": {
                    "animals": len(animals),
                    "enclosures": len(enclosures),
                    "groups": tuple(sorted(group_counts.items())),
                    "care_records": sum(
                        max(
                            0,
                            len(
                                animal_service.effective_history(
                                    principal.household_id, animal.animal_id
                                )
                            )
                            - 1,
                        )
                        for animal in animals
                    ),
                    "expense_total": _friendly_expense_total(expenses),
                    "expense_count": len(expenses),
                },
            },
        )

    @router.get("/reports/{kind}.csv", response_class=PlainTextResponse)
    async def report_csv(request: Request, kind: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if projection_catch_up is not None:
            projection_catch_up()
        try:
            report = report_for(principal, kind)
        except RuntimeError:
            return PlainTextResponse("Report is catching up.", status_code=503)
        if report is None:
            return _access_denied(request, "Report access denied")
        return PlainTextResponse(
            report_service.csv(report),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="snaketracker-{kind}.csv"'},
        )

    @router.get("/reports/{kind}", response_class=HTMLResponse)
    async def report_detail(request: Request, kind: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if projection_catch_up is not None:
            projection_catch_up()
        try:
            report = report_for(principal, kind)
        except RuntimeError:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=503,
                context={
                    "title": "Report is catching up",
                    "message": "The report projection is rebuilding. Try again shortly.",
                },
            )
        if report is None:
            return _access_denied(request, "Report access denied")
        return protected_page(
            request,
            "reports.html",
            principal,
            context={
                "report": report,
                "report_kinds": (),
                "report_kind": kind,
                "report_rows": _report_display_rows(report),
            },
        )

    @router.get("/animals/{animal_id}/analytics", response_class=HTMLResponse)
    async def animal_analytics(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if projection_catch_up is not None:
            projection_catch_up()
        try:
            analytics = analytics_service.for_animal(
                principal.household_id, UUID(animal_id), as_of=datetime.now(UTC).date()
            )
        except (AnalyticsNotAvailableError, ValueError):
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=404,
                context={"title": "Analytics unavailable", "message": "Animal not found."},
            )
        except RuntimeError:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=503,
                context={
                    "title": "Analytics are catching up",
                    "message": "The analytics projection is rebuilding. Try again shortly.",
                },
            )
        return protected_page(
            request,
            "animal_analytics.html",
            principal,
            context={
                "analytics": analytics,
                "insights": _analytics_insights(analytics),
                **animal_experience_context(principal, analytics.animal),
                "active_section": "trends",
            },
        )

    @router.get("/api/v1/animals/{animal_id}/analytics/measurements")
    async def animal_measurement_data(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return JSONResponse({"detail": "Authentication required."}, status_code=401)
        if projection_catch_up is not None:
            projection_catch_up()
        try:
            analytics = analytics_service.for_animal(
                principal.household_id, UUID(animal_id), as_of=datetime.now(UTC).date()
            )
        except (AnalyticsNotAvailableError, ValueError):
            return JSONResponse({"detail": "Animal not found."}, status_code=404)
        except RuntimeError:
            return JSONResponse({"detail": "Analytics are catching up."}, status_code=503)
        payload = {
            "schema_version": 1,
            "animal_id": str(analytics.animal.animal_id),
            "source_cutoff": (
                analytics.source_cutoff.isoformat() if analytics.source_cutoff is not None else None
            ),
            "points": [
                {
                    "kind": item.kind,
                    "occurred_at": item.occurred_at.isoformat(),
                    "value": item.value,
                    "unit": item.unit,
                }
                for item in analytics.measurements
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        etag = f'"{hashlib.sha256(encoded.encode()).hexdigest()}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return JSONResponse(payload, headers={"ETag": etag})

    @router.get("/enclosures", response_class=HTMLResponse)
    async def enclosure_list(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        animals = animal_service.list_profiles(principal.household_id)
        now = datetime.now(UTC)
        return protected_page(
            request,
            "enclosure_list.html",
            principal,
            context={
                "enclosure_rows": _enclosure_collection_rows(
                    enclosures,
                    animals,
                    reminder_fact_service.agenda_for(principal.household_id, now=now),
                    timezone=ZoneInfo(principal.household_timezone),
                    now=now,
                )
            },
        )

    @router.get("/settings/backups", response_class=HTMLResponse)
    async def backup_settings(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "household.manage" not in principal.capabilities:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Backup access denied",
                    "message": "Your household role cannot manage backups.",
                },
                status_code=403,
            )
        return protected_page(
            request,
            "backup_settings.html",
            principal,
            context={
                "errors": {},
                "backup_health": backup_service.health(principal.household_id),
            },
        )

    @router.post("/settings/backups/run", response_class=HTMLResponse)
    async def backup_run_request(request: Request) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        if "household.manage" not in principal.capabilities:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Backup access denied",
                    "message": "Your household role cannot manage backups.",
                },
                status_code=403,
            )
        try:
            backup_service.request_backup(
                RequestBackupCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    idempotency_key=_form_idempotency_key(form),
                )
            )
        except BackupValidationError as error:
            return protected_page(
                request,
                "backup_settings.html",
                principal,
                status_code=422,
                context={
                    "errors": {"form": str(error)},
                    "backup_health": backup_service.health(principal.household_id),
                },
            )
        return RedirectResponse("/settings/backups", status_code=303)

    @router.post("/settings/backups/schedule", response_class=HTMLResponse)
    async def backup_schedule_update(request: Request) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        if "household.manage" not in principal.capabilities:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Backup access denied",
                    "message": "Your household role cannot manage backups.",
                },
                status_code=403,
            )
        try:
            backup_service.configure_schedule(
                ConfigureBackupScheduleCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    enabled=_form_bool(form.get("enabled", ""), "backup schedule"),
                    interval_seconds=_required_int(
                        form.get("interval_seconds", ""), "backup interval"
                    ),
                )
            )
        except (BackupValidationError, FormValidationError) as error:
            return protected_page(
                request,
                "backup_settings.html",
                principal,
                status_code=422,
                context={
                    "errors": {"form": str(error)},
                    "backup_health": backup_service.health(principal.household_id),
                },
            )
        return RedirectResponse("/settings/backups", status_code=303)

    @router.get("/inventory", response_class=HTMLResponse)
    async def inventory_list(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "inventory.view" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        status = "archived" if request.query_params.get("status") == "archived" else "active"
        active_items = inventory_service.list_balances(principal.household_id, status="active")
        archived_items = inventory_service.list_balances(principal.household_id, status="archived")
        items = archived_items if status == "archived" else active_items
        return protected_page(
            request,
            "inventory_list.html",
            principal,
            context={
                "items": items,
                "status": status,
                "inventory_summary": {
                    "active": len(active_items),
                    "archived": len(archived_items),
                    "tracked": len(active_items) + len(archived_items),
                    "attention": sum(
                        1
                        for item in active_items
                        if item.reorder_threshold is not None
                        and item.on_hand_quantity <= item.reorder_threshold
                    ),
                },
            },
        )

    @router.get("/inventory/new", response_class=HTMLResponse)
    async def inventory_new(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        return protected_page(
            request,
            "inventory_new.html",
            principal,
            context={"errors": {}, "values": {}},
        )

    @router.post("/inventory", response_class=HTMLResponse)
    async def inventory_create(request: Request) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        try:
            result = inventory_service.register(
                RegisterInventoryItemCommand(
                    principal.household_id,
                    principal.user_id,
                    uuid4(),
                    _form_idempotency_key(form),
                    str(form.get("name", "")),
                    str(form.get("unit", "")),
                    _optional_int(form.get("reorder_threshold", ""), "reorder threshold"),
                )
            )
        except (InventoryValidationError, FormValidationError) as error:
            return protected_page(
                request,
                "inventory_new.html",
                principal,
                status_code=422,
                context={"errors": {"form": str(error)}, "values": _form_values(form)},
            )
        return RedirectResponse(f"/inventory/{result.item_id}", status_code=303)

    @router.get("/inventory/{item_id}", response_class=HTMLResponse)
    async def inventory_detail(request: Request, item_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "inventory.view" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        try:
            item = inventory_service.balance_for(principal.household_id, UUID(item_id))
        except ValueError:
            item = None
        if item is None:
            return _not_found(request, "Inventory item not found")
        return protected_page(
            request,
            "inventory_detail.html",
            principal,
            context={"item": item, "errors": {}},
        )

    @router.post("/inventory/{item_id}/receive", response_class=HTMLResponse)
    async def inventory_receive(request: Request, item_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        try:
            item_uuid = UUID(item_id)
            inventory_service.receive(
                ReceiveStockCommand(
                    principal.household_id,
                    principal.user_id,
                    item_uuid,
                    uuid4(),
                    _form_idempotency_key(form),
                    _required_int(form.get("expected_stream_version", ""), "stream version"),
                    _required_int(form.get("quantity", ""), "quantity"),
                    str(form.get("reference", "")) or None,
                )
            )
        except (
            InventoryValidationError,
            ExpectedVersionConflictError,
            FormValidationError,
            ValueError,
        ) as error:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=422,
                context={"title": "Inventory could not be updated", "message": str(error)},
            )
        return RedirectResponse(f"/inventory/{item_id}", status_code=303)

    @router.get("/inventory/{item_id}/edit", response_class=HTMLResponse)
    async def inventory_edit(request: Request, item_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        try:
            item = inventory_service.balance_for(principal.household_id, UUID(item_id))
        except ValueError:
            item = None
        if item is None:
            return _not_found(request, "Inventory item not found")
        if item.status != "active":
            return _access_denied(request, "Archived inventory cannot be edited")
        return protected_page(
            request,
            "inventory_edit.html",
            principal,
            context={"item": item, "errors": {}, "values": {}},
        )

    @router.post("/inventory/{item_id}/edit", response_class=HTMLResponse)
    async def inventory_update(request: Request, item_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        try:
            inventory_service.update_item(
                UpdateInventoryItemCommand(
                    principal.household_id,
                    principal.user_id,
                    UUID(item_id),
                    uuid4(),
                    _form_idempotency_key(form),
                    _required_int(form.get("expected_stream_version", ""), "stream version"),
                    str(form.get("name", "")),
                    str(form.get("unit", "")),
                    _optional_int(form.get("reorder_threshold", ""), "reorder threshold"),
                )
            )
        except (
            InventoryValidationError,
            ExpectedVersionConflictError,
            FormValidationError,
            ValueError,
        ) as error:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=422,
                context={"title": "Inventory could not be updated", "message": str(error)},
            )
        return RedirectResponse(f"/inventory/{item_id}", status_code=303)

    @router.post("/inventory/{item_id}/adjust", response_class=HTMLResponse)
    async def inventory_adjust(request: Request, item_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        try:
            inventory_service.adjust(
                AdjustStockCommand(
                    principal.household_id,
                    principal.user_id,
                    UUID(item_id),
                    uuid4(),
                    _form_idempotency_key(form),
                    _required_int(form.get("expected_stream_version", ""), "stream version"),
                    _required_int(form.get("quantity_delta", ""), "quantity adjustment"),
                    str(form.get("reason", "")),
                )
            )
        except (
            InventoryValidationError,
            ExpectedVersionConflictError,
            FormValidationError,
            ValueError,
        ) as error:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=422,
                context={"title": "Inventory could not be adjusted", "message": str(error)},
            )
        return RedirectResponse(f"/inventory/{item_id}", status_code=303)

    @router.post("/inventory/{item_id}/archive", response_class=HTMLResponse)
    async def inventory_archive(request: Request, item_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        try:
            inventory_service.archive_item(
                ArchiveInventoryItemCommand(
                    principal.household_id,
                    principal.user_id,
                    UUID(item_id),
                    uuid4(),
                    _form_idempotency_key(form),
                    _required_int(form.get("expected_stream_version", ""), "stream version"),
                    str(form.get("reason", "")),
                )
            )
        except (
            InventoryValidationError,
            ExpectedVersionConflictError,
            FormValidationError,
            ValueError,
        ) as error:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=422,
                context={"title": "Inventory could not be archived", "message": str(error)},
            )
        return RedirectResponse("/inventory?status=archived", status_code=303)

    @router.post("/inventory/{item_id}/restore", response_class=HTMLResponse)
    async def inventory_restore(request: Request, item_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        try:
            inventory_service.restore_item(
                RestoreInventoryItemCommand(
                    principal.household_id,
                    principal.user_id,
                    UUID(item_id),
                    uuid4(),
                    _form_idempotency_key(form),
                    _required_int(form.get("expected_stream_version", ""), "stream version"),
                    str(form.get("reason", "")),
                )
            )
        except (
            InventoryValidationError,
            ExpectedVersionConflictError,
            FormValidationError,
            ValueError,
        ) as error:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=422,
                context={"title": "Inventory could not be restored", "message": str(error)},
            )
        return RedirectResponse(f"/inventory/{item_id}", status_code=303)

    @router.get("/inventory/{item_id}/{action}", response_class=HTMLResponse)
    async def inventory_action(request: Request, item_id: str, action: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "inventory.manage" not in principal.capabilities:
            return _access_denied(request, "Inventory access denied")
        if action not in {"receive", "adjust", "archive", "restore"}:
            return _not_found(request, "Inventory action not found")
        try:
            item = inventory_service.balance_for(principal.household_id, UUID(item_id))
        except ValueError:
            item = None
        if item is None:
            return _not_found(request, "Inventory item not found")
        action_allowed = (item.status == "active" and action != "restore") or (
            item.status == "archived" and action == "restore"
        )
        if not action_allowed:
            return _access_denied(request, "Inventory action unavailable")
        return protected_page(
            request,
            "inventory_action.html",
            principal,
            context={"item": item, "action": action},
        )

    @router.get("/expenses", response_class=HTMLResponse)
    async def expense_list(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "expense.view" not in principal.capabilities:
            return _access_denied(request, "Expense access denied")
        expenses = expense_service.list_expenses(principal.household_id)
        active = tuple(expense for expense in expenses if expense.status == "active")
        zone = ZoneInfo(principal.household_timezone)
        now = datetime.now(UTC).astimezone(zone)
        current_month = tuple(
            expense
            for expense in active
            if expense.occurred_at.astimezone(zone).year == now.year
            and expense.occurred_at.astimezone(zone).month == now.month
        )
        recent = tuple(
            expense for expense in active if expense.occurred_at >= now - timedelta(days=30)
        )
        category_totals: dict[str, dict[str, int]] = {}
        for expense in active:
            totals = category_totals.setdefault(expense.category, {})
            totals[expense.currency] = totals.get(expense.currency, 0) + expense.amount_minor
        return protected_page(
            request,
            "expense_list.html",
            principal,
            context={
                "expenses": expenses,
                "expense_summary": {
                    "month": _friendly_expense_total(current_month),
                    "recent": _friendly_expense_total(recent),
                    "total": _friendly_expense_total(active),
                    "categories": tuple(
                        (
                            category,
                            " + ".join(
                                _friendly_money(total, currency)
                                for currency, total in sorted(totals.items())
                            ),
                        )
                        for category, totals in sorted(
                            category_totals.items(),
                            key=lambda item: sum(item[1].values()),
                            reverse=True,
                        )
                    ),
                },
            },
        )

    @router.get("/expenses/new", response_class=HTMLResponse)
    async def expense_new(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "expense.manage" not in principal.capabilities:
            return _access_denied(request, "Expense access denied")
        return protected_page(
            request, "expense_new.html", principal, context={"errors": {}, "values": {}}
        )

    @router.post("/expenses", response_class=HTMLResponse)
    async def expense_create(request: Request) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "expense.manage" not in principal.capabilities:
            return _access_denied(request, "Expense access denied")
        try:
            result = expense_service.record(
                RecordExpenseCommand(
                    principal.household_id,
                    principal.user_id,
                    principal.role,
                    uuid4(),
                    _form_idempotency_key(form),
                    _money_minor(form.get("amount", "")),
                    str(form.get("currency", "")),
                    str(form.get("category", "")),
                    str(form.get("payee", "")) or None,
                    str(form.get("reference", "")) or None,
                    str(form.get("notes", "")) or None,
                    _form_datetime(form.get("occurred_at", ""), principal.household_timezone),
                )
            )
        except ExpenseAuthorizationError as error:
            return _access_denied(request, str(error))
        except (ExpenseValidationError, FormValidationError) as error:
            return protected_page(
                request,
                "expense_new.html",
                principal,
                status_code=422,
                context={"errors": {"form": str(error)}, "values": _form_values(form)},
            )
        return RedirectResponse(f"/expenses/{result.expense_id}", status_code=303)

    @router.get("/expenses/{expense_id}", response_class=HTMLResponse)
    async def expense_detail(request: Request, expense_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "expense.view" not in principal.capabilities:
            return _access_denied(request, "Expense access denied")
        try:
            expense = expense_service.expense_for(principal.household_id, UUID(expense_id))
        except ValueError:
            expense = None
        if expense is None:
            return _not_found(request, "Expense not found")
        return protected_page(
            request, "expense_detail.html", principal, context={"expense": expense, "errors": {}}
        )

    @router.post("/expenses/{expense_id}/correct", response_class=HTMLResponse)
    async def expense_correct(request: Request, expense_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "expense.manage" not in principal.capabilities:
            return _access_denied(request, "Expense access denied")
        try:
            expense_uuid = UUID(expense_id)
            expense_service.correct(
                CorrectExpenseCommand(
                    principal.household_id,
                    principal.user_id,
                    principal.role,
                    expense_uuid,
                    UUID(str(form.get("target_event_id", ""))),
                    expense_service.correlation_id_for(principal.household_id, expense_uuid),
                    _form_idempotency_key(form),
                    _required_int(form.get("expected_stream_version", ""), "stream version"),
                    _money_minor(form.get("amount", "")),
                    str(form.get("currency", "")),
                    str(form.get("category", "")),
                    str(form.get("payee", "")) or None,
                    str(form.get("reference", "")) or None,
                    str(form.get("reason", "")),
                )
            )
        except ExpenseAuthorizationError as error:
            return _access_denied(request, str(error))
        except (ExpenseValidationError, FormValidationError, ValueError) as error:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=422,
                context={"title": "Expense could not be corrected", "message": str(error)},
            )
        return RedirectResponse(f"/expenses/{expense_id}", status_code=303)

    @router.post("/expenses/{expense_id}/void", response_class=HTMLResponse)
    async def expense_void(request: Request, expense_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "expense.manage" not in principal.capabilities:
            return _access_denied(request, "Expense access denied")
        try:
            expense_service.void(
                VoidExpenseCommand(
                    principal.household_id,
                    principal.user_id,
                    principal.role,
                    UUID(expense_id),
                    UUID(str(form.get("target_event_id", ""))),
                    expense_service.correlation_id_for(principal.household_id, UUID(expense_id)),
                    _form_idempotency_key(form),
                    _required_int(form.get("expected_stream_version", ""), "stream version"),
                    str(form.get("reason", "")),
                )
            )
        except ExpenseAuthorizationError as error:
            return _access_denied(request, str(error))
        except (ExpenseValidationError, FormValidationError, ValueError) as error:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=422,
                context={"title": "Expense could not be voided", "message": str(error)},
            )
        return RedirectResponse(f"/expenses/{expense_id}", status_code=303)

    @router.get("/reminders", response_class=HTMLResponse)
    async def reminder_list(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "reminder.view" not in principal.capabilities:
            return _access_denied(request, "Reminder access denied")
        now = datetime.now(UTC)
        animals = animal_service.list_profiles(principal.household_id)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        agenda = _agenda_rows(
            reminder_fact_service.agenda_for(principal.household_id, now=now),
            animals=animals,
            enclosures=enclosures,
            timezone=ZoneInfo(principal.household_timezone),
            now=now,
        )
        return protected_page(
            request,
            "reminder_list.html",
            principal,
            context={
                "agenda_groups": (
                    ("overdue", "Overdue", agenda["overdue"]),
                    ("due_today", "Due today", agenda["due_today"]),
                    ("upcoming", "Upcoming", agenda["upcoming"]),
                ),
            },
        )

    @router.get("/reminders/new", response_class=HTMLResponse)
    async def reminder_new(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "reminder.manage" not in principal.capabilities:
            return _access_denied(request, "Reminder access denied")
        animals = animal_service.list_profiles(principal.household_id)
        enclosures = enclosure_service.list_profiles(principal.household_id)
        return protected_page(
            request,
            "reminder_new.html",
            principal,
            context={
                "errors": {},
                "values": {},
                "reminder_subjects": _reminder_subject_rows(animals, enclosures),
            },
        )

    @router.post("/reminders", response_class=HTMLResponse)
    async def reminder_create(request: Request) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "reminder.manage" not in principal.capabilities:
            return _access_denied(request, "Reminder access denied")
        try:
            schedule_kind = str(form.get("schedule_kind", ""))
            anchor_value = str(form.get("anchor_at", "")).strip()
            override_value = str(form.get("override_due_at", "")).strip()
            subject_type, separator, subject_id_value = str(form.get("subject", "")).partition(":")
            if not separator or subject_type not in {"animal", "enclosure"}:
                raise FormValidationError("Choose a valid reminder subject.")
            result = reminder_rule_service.create(
                CreateReminderRuleCommand(
                    principal.household_id,
                    principal.user_id,
                    uuid4(),
                    _form_idempotency_key(form),
                    subject_type,
                    UUID(subject_id_value),
                    str(form.get("reminder_type", "")),
                    schedule_kind,
                    _required_int(form.get("interval_days", ""), "interval"),
                    (
                        _form_datetime(anchor_value, principal.household_timezone).isoformat()
                        if anchor_value
                        else None
                    ),
                    (
                        _form_datetime(override_value, principal.household_timezone).isoformat()
                        if override_value
                        else None
                    ),
                    True,
                    str(form.get("channel", "local")),
                )
            )
        except (ReminderValidationError, FormValidationError, ValueError) as error:
            animals = animal_service.list_profiles(principal.household_id)
            enclosures = enclosure_service.list_profiles(principal.household_id)
            return protected_page(
                request,
                "reminder_new.html",
                principal,
                status_code=422,
                context={
                    "errors": {"form": str(error)},
                    "values": _form_values(form),
                    "reminder_subjects": _reminder_subject_rows(animals, enclosures),
                },
            )
        return RedirectResponse(f"/reminders#{result.rule_id}", status_code=303)

    @router.post("/reminders/{rule_id}/disable", response_class=HTMLResponse)
    async def reminder_disable(request: Request, rule_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "reminder.manage" not in principal.capabilities:
            return _access_denied(request, "Reminder access denied")
        try:
            current = reminder_projection.rule_for(principal.household_id, UUID(rule_id))
            if current is None:
                raise ReminderValidationError("Reminder rule does not exist.")
            reminder_rule_service.disable(
                DisableReminderRuleCommand(
                    principal.household_id,
                    principal.user_id,
                    current.rule_id,
                    current.stream_version,
                    reminder_rule_service.correlation_id_for(
                        principal.household_id, current.rule_id
                    ),
                    _form_idempotency_key(form),
                    str(form.get("reason", "")),
                )
            )
        except (ReminderValidationError, ValueError) as error:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=422,
                context={"title": "Reminder could not be disabled", "message": str(error)},
            )
        return RedirectResponse("/reminders", status_code=303)

    @router.get("/operations/jobs", response_class=HTMLResponse)
    async def operations_jobs(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "operations.view" not in principal.capabilities:
            return _access_denied(request, "Operations access denied")
        return protected_page(
            request,
            "operations_jobs.html",
            principal,
            context={"jobs": job_repository.list_for(principal.household_id)},
        )

    @router.get("/animals/new", response_class=HTMLResponse)
    async def animal_new(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return protected_page(
            request,
            "animal_new.html",
            principal,
            context={
                "errors": {},
                "values": {},
                "animal_types": _animal_type_options(),
            },
        )

    @router.get("/enclosures/new", response_class=HTMLResponse)
    async def enclosure_new(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return protected_page(
            request,
            "enclosure_new.html",
            principal,
            context={"errors": {}, "values": {}},
        )

    @router.post("/enclosures", response_class=HTMLResponse)
    async def enclosure_create(request: Request) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        values = {
            name: str(form.get(name, "")).strip() for name in ("name", "enclosure_type", "notes")
        }
        try:
            result = enclosure_service.register(
                RegisterEnclosureCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    **values,
                )
            )
        except EnclosureValidationError as error:
            return protected_page(
                request,
                "enclosure_new.html",
                principal,
                status_code=422,
                context={"errors": {"form": str(error)}, "values": values},
            )
        return RedirectResponse(f"/enclosures/{result.enclosure_id}", status_code=303)

    @router.get("/enclosures/{enclosure_id}", response_class=HTMLResponse)
    async def enclosure_profile(request: Request, enclosure_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        try:
            enclosure_uuid = UUID(enclosure_id)
        except ValueError:
            enclosure_uuid = None
        profile = (
            enclosure_service.profile_for(principal.household_id, enclosure_uuid)
            if enclosure_uuid is not None
            else None
        )
        if profile is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Enclosure not found",
                    "message": "Return to your household workspace and try again.",
                },
                status_code=404,
            )
        assert enclosure_uuid is not None
        return protected_page(
            request,
            "enclosure_profile.html",
            principal,
            context={
                "enclosure": profile,
                "occupants": enclosure_service.occupants(principal.household_id, enclosure_uuid),
                "enclosure_statuses": tuple(sorted(ENCLOSURE_STATUSES)),
            },
        )

    @router.get("/enclosures/{enclosure_id}/edit", response_class=HTMLResponse)
    async def enclosure_edit(request: Request, enclosure_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        try:
            enclosure = enclosure_service.profile_for(principal.household_id, UUID(enclosure_id))
        except ValueError:
            enclosure = None
        if enclosure is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Enclosure not found",
                    "message": "Return to your enclosure list and try again.",
                },
                status_code=404,
            )
        return protected_page(
            request,
            "enclosure_edit.html",
            principal,
            context={"enclosure": enclosure, "errors": {}},
        )

    @router.post("/enclosures/{enclosure_id}/edit", response_class=HTMLResponse)
    async def enclosure_edit_submit(request: Request, enclosure_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            enclosure_uuid = UUID(enclosure_id)
            if enclosure_service.profile_for(principal.household_id, enclosure_uuid) is None:
                raise FormValidationError("Enclosure not found.")
            enclosure_service.update_profile(
                UpdateEnclosureProfileCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    enclosure_id=enclosure_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    name=str(form.get("name", "")),
                    enclosure_type=str(form.get("enclosure_type", "")),
                    notes=str(form.get("notes", "")),
                )
            )
        except (EnclosureValidationError, FormValidationError, ValueError) as error:
            return _enclosure_edit_error(
                request, principal, enclosure_id, str(error), enclosure_service
            )
        return RedirectResponse(f"/enclosures/{enclosure_id}", status_code=303)

    @router.post("/enclosures/{enclosure_id}/status", response_class=HTMLResponse)
    async def enclosure_status_change(request: Request, enclosure_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            enclosure_uuid = UUID(enclosure_id)
            if enclosure_service.profile_for(principal.household_id, enclosure_uuid) is None:
                raise FormValidationError("Enclosure not found.")
            enclosure_service.change_status(
                ChangeEnclosureStatusCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    enclosure_id=enclosure_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    status=str(form.get("status", "")),
                    notes=str(form.get("notes", "")),
                )
            )
        except (EnclosureValidationError, FormValidationError, ValueError) as error:
            return _enclosure_form_error(
                request, principal, enclosure_id, str(error), enclosure_service
            )
        return RedirectResponse(f"/enclosures/{enclosure_id}", status_code=303)

    @router.post("/enclosures/{enclosure_id}/cleanings", response_class=HTMLResponse)
    async def enclosure_cleaning_create(request: Request, enclosure_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            enclosure_uuid = UUID(enclosure_id)
            if enclosure_service.profile_for(principal.household_id, enclosure_uuid) is None:
                raise FormValidationError("Enclosure not found.")
            enclosure_service.record_cleaning(
                RecordCleaningCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    enclosure_id=enclosure_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    notes=str(form.get("notes", "")),
                )
            )
        except (EnclosureValidationError, FormValidationError, ValueError) as error:
            return _enclosure_form_error(
                request, principal, enclosure_id, str(error), enclosure_service
            )
        return RedirectResponse(
            "/home" if str(form.get("return_to", "")) == "today" else f"/enclosures/{enclosure_id}",
            status_code=303,
        )

    @router.post("/enclosures/{enclosure_id}/water-changes", response_class=HTMLResponse)
    async def enclosure_water_change_create(request: Request, enclosure_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            enclosure_uuid = UUID(enclosure_id)
            if enclosure_service.profile_for(principal.household_id, enclosure_uuid) is None:
                raise FormValidationError("Enclosure not found.")
            enclosure_service.record_water_change(
                RecordWaterChangeCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    enclosure_id=enclosure_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    notes=str(form.get("notes", "")),
                )
            )
        except (EnclosureValidationError, FormValidationError, ValueError) as error:
            return _enclosure_form_error(
                request, principal, enclosure_id, str(error), enclosure_service
            )
        return RedirectResponse(
            "/home" if str(form.get("return_to", "")) == "today" else f"/enclosures/{enclosure_id}",
            status_code=303,
        )

    @router.post("/animals", response_class=HTMLResponse)
    async def animal_create(request: Request) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        values = {
            name: str(form.get(name, "")).strip()
            for name in (
                "name",
                "species",
                "morph",
                "genetics",
                "sex",
                "birth_hatch_date",
                "acquisition_date",
                "breeder_source",
                "notes",
            )
        }
        values["animal_type"] = str(form.get("animal_type", "snake")).strip()
        try:
            result = animal_service.register(
                RegisterAnimalCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    **values,
                )
            )
        except AnimalValidationError as error:
            return protected_page(
                request,
                "animal_new.html",
                principal,
                status_code=422,
                context={
                    "errors": {"form": str(error)},
                    "values": values,
                    "animal_types": _animal_type_options(),
                },
            )
        return RedirectResponse(f"/animals/{result.animal_id}", status_code=303)

    @router.get("/animals/{animal_id}", response_class=HTMLResponse)
    async def animal_profile(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        try:
            profile = animal_service.profile_for(principal.household_id, UUID(animal_id))
        except ValueError:
            profile = None
        if profile is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Animal not found",
                    "message": "Return to your animal list and try again.",
                },
                status_code=404,
            )
        return protected_page(
            request,
            "animal_profile.html",
            principal,
            context={
                **animal_experience_context(principal, profile),
                "active_section": "overview",
            },
        )

    @router.get("/animals/{animal_id}/care", response_class=HTMLResponse)
    async def animal_care(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        try:
            profile = animal_service.profile_for(principal.household_id, UUID(animal_id))
        except ValueError:
            profile = None
        if profile is None:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=404,
                context={
                    "title": "Animal not found",
                    "message": "Return to your animal list and try again.",
                },
            )
        return protected_page(
            request,
            "animal_care.html",
            principal,
            context={
                **animal_experience_context(principal, profile),
                "active_section": "care",
            },
        )

    @router.get(
        "/animals/{animal_id}/care-schedule/{reminder_type}/edit",
        response_class=HTMLResponse,
    )
    async def animal_care_schedule_edit(
        request: Request, animal_id: str, reminder_type: str
    ) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        if "reminder.manage" not in principal.capabilities:
            return _access_denied(request, "Care schedule access denied")
        try:
            animal = animal_service.profile_for(principal.household_id, UUID(animal_id))
        except ValueError:
            animal = None
        if animal is None:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=404,
                context={"title": "Animal not found", "message": "Return to Animals."},
            )
        context = animal_experience_context(principal, animal)
        schedule = next(
            (row for row in context["care_schedules"] if row["reminder_type"] == reminder_type),
            None,
        )
        if schedule is None:
            return protected_page(
                request,
                "error.html",
                principal,
                status_code=404,
                context={
                    "title": "Schedule not available",
                    "message": "This care schedule is not supported for this profile.",
                },
            )
        return protected_page(
            request,
            "animal_schedule_edit.html",
            principal,
            context={**context, "schedule": schedule, "active_section": "care", "errors": {}},
        )

    @router.post(
        "/animals/{animal_id}/care-schedule/{reminder_type}",
        response_class=HTMLResponse,
    )
    async def animal_care_schedule_save(
        request: Request, animal_id: str, reminder_type: str
    ) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        if "reminder.manage" not in principal.capabilities:
            return _access_denied(request, "Care schedule access denied")
        try:
            animal_uuid = UUID(animal_id)
            profile = animal_service.profile_for(principal.household_id, animal_uuid)
            if profile is None:
                raise FormValidationError("Animal not found.")
            capability = CARE_SCHEDULE_CAPABILITIES.get(reminder_type)
            if capability is None or reminder_type not in profile.reminder_kinds:
                raise FormValidationError("Care schedule type is not supported.")
            _title, subject_type, _source = capability
            if subject_type == "animal":
                subject_id = profile.animal_id
            else:
                if profile.current_enclosure_id is None:
                    raise FormValidationError(
                        "Assign an enclosure before configuring this care schedule."
                    )
                subject_id = profile.current_enclosure_id
            enabled = str(form.get("enabled", "")).lower() == "true"
            existing = _subject_schedule_rule(
                reminder_projection,
                principal.household_id,
                subject_type,
                subject_id,
                reminder_type,
            )
            interval_value = str(form.get("interval_days", "")).strip()
            if enabled and not interval_value:
                raise FormValidationError("Interval is required when the schedule is enabled.")
            interval_days = (
                _required_int(interval_value, "interval")
                if interval_value
                else existing.interval_days
                if existing is not None
                else 1
            )
            override_value = str(form.get("override_due_at", "")).strip()
            reminder_rule_service.save_subject_schedule(
                SaveSubjectScheduleCommand(
                    principal.household_id,
                    principal.user_id,
                    uuid4(),
                    _form_idempotency_key(form),
                    _required_int(form.get("expected_stream_version", ""), "stream version"),
                    subject_type,
                    subject_id,
                    reminder_type,
                    interval_days,
                    (
                        _form_datetime(override_value, principal.household_timezone).isoformat()
                        if override_value
                        else None
                    ),
                    enabled,
                )
            )
        except (ReminderValidationError, FormValidationError, ValueError) as error:
            try:
                animal = animal_service.profile_for(principal.household_id, UUID(animal_id))
            except ValueError:
                animal = None
            if animal is None:
                return protected_page(
                    request,
                    "error.html",
                    principal,
                    status_code=404,
                    context={"title": "Animal not found", "message": "Return to Animals."},
                )
            context = animal_experience_context(principal, animal)
            schedule = next(
                (row for row in context["care_schedules"] if row["reminder_type"] == reminder_type),
                None,
            )
            if schedule is None:
                return protected_page(
                    request,
                    "error.html",
                    principal,
                    status_code=422,
                    context={"title": "Schedule not available", "message": str(error)},
                )
            return protected_page(
                request,
                "animal_schedule_edit.html",
                principal,
                status_code=422,
                context={
                    **context,
                    "schedule": schedule,
                    "active_section": "care",
                    "errors": {"form": str(error)},
                },
            )
        destination = (
            f"/animals/{animal_id}/care"
            if str(form.get("return_to", "")) == "care"
            else f"/animals/{animal_id}#care-schedule"
        )
        return RedirectResponse(destination, status_code=303)

    def care_form_response(
        request: Request,
        animal_id: str,
        care_kind: str,
        *,
        principal: Principal | None = None,
        status_code: int = 200,
        error: str | None = None,
        values: dict[str, str] | None = None,
    ) -> Response:
        current_principal = principal or principal_for(request, audit_denial=True)
        if current_principal is None:
            return RedirectResponse("/login", status_code=303)
        return _animal_care_form_page(
            request,
            animal_id,
            care_kind,
            principal=current_principal,
            protected_page=protected_page,
            animal_service=animal_service,
            inventory_service=inventory_service,
            status_code=status_code,
            error=error,
            values=values,
        )

    @router.get("/animals/{animal_id}/feedings/new", response_class=HTMLResponse)
    async def animal_feeding_new(request: Request, animal_id: str) -> Response:
        return care_form_response(request, animal_id, "feeding")

    @router.get("/animals/{animal_id}/weights/new", response_class=HTMLResponse)
    async def animal_weight_new(request: Request, animal_id: str) -> Response:
        return care_form_response(request, animal_id, "weight")

    @router.get("/animals/{animal_id}/lengths/new", response_class=HTMLResponse)
    async def animal_length_new(request: Request, animal_id: str) -> Response:
        return care_form_response(request, animal_id, "length")

    @router.get("/animals/{animal_id}/sheds/new", response_class=HTMLResponse)
    async def animal_shed_new(request: Request, animal_id: str) -> Response:
        return care_form_response(request, animal_id, "shed")

    @router.get("/animals/{animal_id}/baths/new", response_class=HTMLResponse)
    async def animal_bath_new(request: Request, animal_id: str) -> Response:
        return care_form_response(request, animal_id, "bath")

    @router.get("/animals/{animal_id}/molts/new", response_class=HTMLResponse)
    async def animal_molt_new(request: Request, animal_id: str) -> Response:
        return care_form_response(request, animal_id, "molt")

    @router.get("/animals/{animal_id}/premolt-observations/new", response_class=HTMLResponse)
    async def animal_premolt_new(request: Request, animal_id: str) -> Response:
        return care_form_response(request, animal_id, "premolt")

    @router.get("/animals/{animal_id}/mistings/new", response_class=HTMLResponse)
    async def animal_misting_new(request: Request, animal_id: str) -> Response:
        return care_form_response(request, animal_id, "misting")

    @router.get("/animals/{animal_id}/photo", response_class=HTMLResponse)
    async def animal_photo(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return animal_management_response(request, principal, animal_id, "photo")

    @router.get("/animals/{animal_id}/enclosure", response_class=HTMLResponse)
    async def animal_enclosure(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return animal_management_response(request, principal, animal_id, "enclosure")

    @router.get("/animals/{animal_id}/status", response_class=HTMLResponse)
    async def animal_status(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return animal_management_response(request, principal, animal_id, "status")

    @router.post("/animals/{animal_id}/photo", response_class=HTMLResponse)
    async def animal_photo_upload(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(
            request,
            max_files=1,
            max_fields=8,
            max_part_size=MAX_PROFILE_PHOTO_BYTES,
            parse_error_message="Choose a smaller profile photo and try again.",
        )
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        upload = form.get("photo")
        try:
            animal_uuid = UUID(animal_id)
            if not isinstance(upload, UploadFile):
                raise FormValidationError("Choose a profile photo to upload.")
            staged = attachment_service.stage_profile_photo(
                StageProfilePhotoCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    idempotency_key=f"{_form_idempotency_key(form)}:stage",
                    content=await upload.read(MAX_PROFILE_PHOTO_BYTES + 1),
                    declared_media_type=upload.content_type or "",
                )
            )
            finalized = attachment_service.finalize_profile_photo(
                FinalizeProfilePhotoCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    staged_attachment_id=staged.staged_attachment_id,
                    idempotency_key=f"{_form_idempotency_key(form)}:finalize",
                )
            )
            attachment_service.select_profile_photo(
                SelectProfilePhotoCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    attachment_version_id=finalized.attachment_version_id,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                )
            )
        except (AttachmentValidationError, FormValidationError, ValueError) as error:
            return animal_management_response(
                request, principal, animal_id, "photo", status_code=422, error=str(error)
            )
        finally:
            if isinstance(upload, UploadFile):
                await upload.close()
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.get("/attachments/{attachment_version_id}")
    async def attachment_delivery(request: Request, attachment_version_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        try:
            delivered = attachment_service.load_profile_photo(
                principal.household_id, UUID(attachment_version_id)
            )
        except (AttachmentValidationError, ValueError):
            return Response(status_code=404)
        extension = "png" if delivered.finalized.metadata.media_type == "image/png" else "jpg"
        return Response(
            content=delivered.content,
            media_type=delivered.finalized.metadata.media_type,
            headers={
                "Cache-Control": "private, immutable, max-age=31536000",
                "Content-Disposition": f'inline; filename="profile-photo.{extension}"',
                "Cross-Origin-Resource-Policy": "same-origin",
            },
        )

    @router.get("/animals/{animal_id}/edit", response_class=HTMLResponse)
    async def animal_edit(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        try:
            profile = animal_service.profile_for(principal.household_id, UUID(animal_id))
        except ValueError:
            profile = None
        if profile is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Animal not found",
                    "message": "Return to your animal list and try again.",
                },
                status_code=404,
            )
        return protected_page(
            request,
            "animal_edit.html",
            principal,
            context={"animal": profile, "errors": {}},
        )

    @router.post("/animals/{animal_id}/edit", response_class=HTMLResponse)
    async def animal_edit_submit(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            profile = animal_service.profile_for(principal.household_id, animal_uuid)
            if profile is None:
                raise FormValidationError("Animal not found.")
            animal_service.update_profile(
                UpdateAnimalProfileCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    name=str(form.get("name", "")),
                    species=str(form.get("species", "")),
                    morph=str(form.get("morph", "")),
                    genetics=str(form.get("genetics", "")),
                    sex=str(form.get("sex", "")),
                    birth_hatch_date=str(form.get("birth_hatch_date", "")),
                    acquisition_date=str(form.get("acquisition_date", "")),
                    breeder_source=str(form.get("breeder_source", "")),
                    notes=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return _animal_edit_error(request, principal, animal_id, str(error), animal_service)
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/status", response_class=HTMLResponse)
    async def animal_status_change(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            if animal_service.profile_for(principal.household_id, animal_uuid) is None:
                raise FormValidationError("Animal not found.")
            animal_service.change_status(
                ChangeAnimalStatusCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    status=str(form.get("status", "")),
                    notes=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return animal_management_response(
                request, principal, animal_id, "status", status_code=422, error=str(error)
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/enclosure", response_class=HTMLResponse)
    async def animal_enclosure_assign(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            enclosure_uuid = UUID(str(form.get("enclosure_id", "")))
            if animal_service.profile_for(principal.household_id, animal_uuid) is None:
                raise FormValidationError("Animal not found.")
            if enclosure_service.profile_for(principal.household_id, enclosure_uuid) is None:
                raise FormValidationError("Enclosure not found.")
            animal_service.assign_enclosure(
                AssignEnclosureCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    enclosure_id=enclosure_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    notes=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return animal_management_response(
                request, principal, animal_id, "enclosure", status_code=422, error=str(error)
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/feedings", response_class=HTMLResponse)
    async def animal_feeding_create(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            if animal_service.profile_for(principal.household_id, animal_uuid) is None:
                raise FormValidationError("Animal not found.")
            inventory_item_id, inventory_version = _inventory_reference(form)
            animal_service.record_feeding(
                RecordFeedingCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    prey_type=str(form.get("prey_type", "")),
                    prey_size=str(form.get("prey_size", "")),
                    prey_weight_grams=_optional_int(
                        form.get("prey_weight_grams", ""), "prey weight"
                    ),
                    preparation_method=str(form.get("preparation_method", "")),
                    quantity=_required_int(form.get("quantity", ""), "quantity"),
                    outcome=str(form.get("outcome", "")),
                    notes=str(form.get("notes", "")),
                    inventory_item_id=inventory_item_id,
                    inventory_expected_stream_version=inventory_version,
                    inventory_quantity=_optional_int(
                        form.get("inventory_quantity", ""), "inventory quantity"
                    ),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return care_form_response(
                request,
                animal_id,
                "feeding",
                principal=principal,
                status_code=422,
                error=str(error),
                values=_form_values(form),
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/weights", response_class=HTMLResponse)
    async def animal_weight_create(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            if animal_service.profile_for(principal.household_id, animal_uuid) is None:
                raise FormValidationError("Animal not found.")
            animal_service.record_weight(
                RecordWeightCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    weight_grams=_required_int(form.get("weight_grams", ""), "weight"),
                    notes=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return care_form_response(
                request,
                animal_id,
                "weight",
                principal=principal,
                status_code=422,
                error=str(error),
                values=_form_values(form),
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/lengths", response_class=HTMLResponse)
    async def animal_length_create(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            if animal_service.profile_for(principal.household_id, animal_uuid) is None:
                raise FormValidationError("Animal not found.")
            animal_service.record_length(
                RecordLengthCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    length_mm=_required_int(form.get("length_mm", ""), "length"),
                    notes=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return care_form_response(
                request,
                animal_id,
                "length",
                principal=principal,
                status_code=422,
                error=str(error),
                values=_form_values(form),
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/sheds", response_class=HTMLResponse)
    async def animal_shed_create(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            if animal_service.profile_for(principal.household_id, animal_uuid) is None:
                raise FormValidationError("Animal not found.")
            animal_service.record_shed(
                RecordShedCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    blue_state=_form_bool(form.get("blue_state", ""), "blue-state"),
                    completed=_form_bool(form.get("completed", ""), "completion"),
                    result=(str(form.get("result", "")).strip() or None),
                    notes=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return care_form_response(
                request,
                animal_id,
                "shed",
                principal=principal,
                status_code=422,
                error=str(error),
                values=_form_values(form),
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/baths", response_class=HTMLResponse)
    async def animal_bath_create(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            if animal_service.profile_for(principal.household_id, animal_uuid) is None:
                raise FormValidationError("Animal not found.")
            animal_service.record_bath(
                RecordBathCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    duration_minutes=_required_int(form.get("duration_minutes", ""), "duration"),
                    reason=str(form.get("reason", "")),
                    notes=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return care_form_response(
                request,
                animal_id,
                "bath",
                principal=principal,
                status_code=422,
                error=str(error),
                values=_form_values(form),
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/molts", response_class=HTMLResponse)
    async def animal_molt_create(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        try:
            animal_uuid = UUID(animal_id)
            animal_service.record_molt(
                RecordMoltCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    result=str(form.get("result", "")),
                    observation=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return care_form_response(
                request,
                animal_id,
                "molt",
                principal=principal,
                status_code=422,
                error=str(error),
                values=_form_values(form),
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/premolt-observations", response_class=HTMLResponse)
    async def animal_premolt_create(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        try:
            animal_uuid = UUID(animal_id)
            animal_service.record_premolt(
                RecordPremoltCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    observed=_form_bool(form.get("observed", ""), "premolt state"),
                    observation=str(form.get("notes", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return care_form_response(
                request,
                animal_id,
                "premolt",
                principal=principal,
                status_code=422,
                error=str(error),
                values=_form_values(form),
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.post("/animals/{animal_id}/mistings", response_class=HTMLResponse)
    async def animal_misting_create(request: Request, animal_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None and form is not None
        try:
            animal_uuid = UUID(animal_id)
            profile = animal_service.profile_for(principal.household_id, animal_uuid)
            if profile is None:
                raise FormValidationError("Animal not found.")
            if profile.current_enclosure_id is None:
                raise FormValidationError("Assign an enclosure before recording misting care.")
            enclosure_service.record_misting(
                RecordMistingCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    enclosure_id=profile.current_enclosure_id,
                    animal_id=animal_uuid,
                    correlation_id=uuid4(),
                    idempotency_key=_form_idempotency_key(form),
                    occurred_at=_form_datetime(
                        form.get("occurred_at", ""), principal.household_timezone
                    ),
                    duration_seconds=_optional_int(
                        form.get("duration_seconds", ""), "misting duration"
                    ),
                    notes=str(form.get("notes", "")),
                )
            )
        except (EnclosureValidationError, FormValidationError, ValueError) as error:
            return care_form_response(
                request,
                animal_id,
                "misting",
                principal=principal,
                status_code=422,
                error=str(error),
                values=_form_values(form),
            )
        return RedirectResponse(
            _care_return_location(animal_id, form.get("return_to", "animal")), status_code=303
        )

    @router.get("/animals/{animal_id}/events/{event_id}/correct", response_class=HTMLResponse)
    async def animal_event_correction_form(
        request: Request, animal_id: str, event_id: str
    ) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        try:
            animal_uuid = UUID(animal_id)
            event_uuid = UUID(event_id)
            profile = animal_service.profile_for(principal.household_id, animal_uuid)
            target = _animal_event(animal_service, principal.household_id, animal_uuid, event_uuid)
        except ValueError:
            profile = None
            target = None
        if profile is None or target is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Care record not found",
                    "message": "Return to the animal timeline and try again.",
                },
                status_code=404,
            )
        if (
            target.event_id
            not in _timeline_action_ids(
                animal_service.audit_history(principal.household_id, animal_uuid)
            )["correctable_event_ids"]
        ):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Care record cannot be corrected",
                    "message": "Use the available historical controls instead.",
                },
                status_code=422,
            )
        return protected_page(
            request,
            "animal_event_correct.html",
            principal,
            context={"animal": profile, "target": target, "errors": {}},
        )

    @router.post("/animals/{animal_id}/events/{event_id}/correct", response_class=HTMLResponse)
    async def animal_event_correct(request: Request, animal_id: str, event_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            event_uuid = UUID(event_id)
            profile = animal_service.profile_for(principal.household_id, animal_uuid)
            target = _animal_event(animal_service, principal.household_id, animal_uuid, event_uuid)
            if profile is None or target is None:
                raise FormValidationError("Care record not found.")
            if (
                target.event_id
                not in _timeline_action_ids(
                    animal_service.audit_history(principal.household_id, animal_uuid)
                )["correctable_event_ids"]
            ):
                raise FormValidationError("This care record cannot be corrected.")
            _correct_animal_event_from_form(animal_service, principal, animal_uuid, target, form)
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            if (
                "profile" not in locals()
                or profile is None
                or "target" not in locals()
                or target is None
            ):
                return templates.TemplateResponse(
                    request,
                    "error.html",
                    {
                        "title": "Care record not found",
                        "message": "Return to the animal timeline and try again.",
                    },
                    status_code=404,
                )
            return protected_page(
                request,
                "animal_event_correct.html",
                principal,
                status_code=422,
                context={"animal": profile, "target": target, "errors": {"form": str(error)}},
            )
        return RedirectResponse(f"/animals/{animal_id}/timeline", status_code=303)

    @router.post("/animals/{animal_id}/events/{event_id}/void", response_class=HTMLResponse)
    async def animal_event_void(request: Request, animal_id: str, event_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            event_uuid = UUID(event_id)
            profile = animal_service.profile_for(principal.household_id, animal_uuid)
            target = _animal_event(animal_service, principal.household_id, animal_uuid, event_uuid)
            if profile is None or target is None:
                raise FormValidationError("Care record not found.")
            animal_service.void_event(
                VoidAnimalEventCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    animal_id=animal_uuid,
                    target_event_id=target.event_id,
                    idempotency_key=_form_idempotency_key(form),
                    reason=str(form.get("reason", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return _animal_timeline_error(
                request,
                principal,
                animal_id,
                str(error),
                animal_service,
                enclosure_service,
            )
        return RedirectResponse(f"/animals/{animal_id}/timeline", status_code=303)

    @router.post("/animals/{animal_id}/events/{event_id}/reinstate", response_class=HTMLResponse)
    async def animal_event_reinstate(request: Request, animal_id: str, event_id: str) -> Response:
        principal, form, rejection = await protected_form(request)
        if rejection is not None:
            return rejection
        assert principal is not None
        assert form is not None
        try:
            animal_uuid = UUID(animal_id)
            event_uuid = UUID(event_id)
            profile = animal_service.profile_for(principal.household_id, animal_uuid)
            target = _animal_event(animal_service, principal.household_id, animal_uuid, event_uuid)
            if profile is None or target is None:
                raise FormValidationError("Care record not found.")
            animal_service.reinstate_event(
                ReinstateAnimalEventCommand(
                    household_id=principal.household_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    animal_id=animal_uuid,
                    target_event_id=target.event_id,
                    idempotency_key=_form_idempotency_key(form),
                    reason=str(form.get("reason", "")),
                )
            )
        except (AnimalValidationError, FormValidationError, ValueError) as error:
            return _animal_timeline_error(
                request,
                principal,
                animal_id,
                str(error),
                animal_service,
                enclosure_service,
            )
        return RedirectResponse(f"/animals/{animal_id}/timeline", status_code=303)

    @router.get("/animals/{animal_id}/timeline", response_class=HTMLResponse)
    async def animal_timeline(request: Request, animal_id: str) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        try:
            animal_uuid = UUID(animal_id)
            profile = animal_service.profile_for(principal.household_id, animal_uuid)
        except ValueError:
            profile = None
        if profile is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Animal not found",
                    "message": "Return to your animal list and try again.",
                },
                status_code=404,
            )
        return protected_page(
            request,
            "animal_timeline.html",
            principal,
            context={
                **animal_experience_context(principal, profile),
                "active_section": "history",
                **_timeline_context(
                    animal_service,
                    enclosure_service,
                    principal.household_id,
                    animal_uuid,
                ),
            },
        )

    @router.get("/animals/{animal_id}/feedings", response_class=HTMLResponse)
    async def animal_feeding_history(request: Request, animal_id: str) -> Response:
        return _animal_history_page(
            request,
            animal_id,
            principal_for=principal_for,
            protected_page=protected_page,
            animal_service=animal_service,
            enclosure_service=enclosure_service,
            event_types=frozenset({"animal.feeding_recorded", "animal.feeding_corrected"}),
            page_title="Feeding history",
            page_description="Effective feeding history, including accepted corrections.",
            empty_message="No feeding records yet.",
        )

    @router.get("/animals/{animal_id}/measurements", response_class=HTMLResponse)
    async def animal_measurement_history(request: Request, animal_id: str) -> Response:
        return _animal_history_page(
            request,
            animal_id,
            principal_for=principal_for,
            protected_page=protected_page,
            animal_service=animal_service,
            enclosure_service=enclosure_service,
            event_types=frozenset(
                {
                    "animal.weight_recorded",
                    "animal.weight_corrected",
                    "animal.length_recorded",
                    "animal.length_corrected",
                }
            ),
            page_title="Measurement history",
            page_description="Effective weight and length history.",
            empty_message="No measurement records yet.",
        )

    @router.post("/logout")
    async def logout(request: Request) -> Response:
        if not _form_request_valid(request, expected_origin):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Return home and try again.",
                },
                status_code=403,
            )
        token = request.cookies.get(SESSION_COOKIE)
        submitted = str((await request.form()).get("csrf_token", ""))
        if token is None or not identity_service.verify_csrf(token, submitted):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "title": "Request could not be verified",
                    "message": "Return home and try again.",
                },
                status_code=403,
            )
        identity_service.logout(token, correlation_id=uuid4())
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")
        return response

    return router


def _animal_form_error(
    request: Request,
    principal: Principal,
    animal_id: str,
    message: str,
    animal_service: AnimalService,
    enclosure_service: EnclosureService | None = None,
    reminder_projection: ReminderProjection | None = None,
) -> HTMLResponse:
    try:
        profile = animal_service.profile_for(principal.household_id, UUID(animal_id))
    except ValueError:
        profile = None
    if profile is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"title": "Animal not found", "message": "Return to your animal list and try again."},
            status_code=404,
        )
    enclosures = (
        enclosure_service.list_profiles(principal.household_id)
        if enclosure_service is not None
        else ()
    )
    current_enclosure = next(
        (
            enclosure
            for enclosure in enclosures
            if enclosure.enclosure_id == profile.current_enclosure_id
        ),
        None,
    )
    recent_events = _recent_care_views(
        animal_service.effective_history(principal.household_id, profile.animal_id),
        enclosure_names={enclosure.enclosure_id: enclosure.name for enclosure in enclosures},
    )
    return templates.TemplateResponse(
        request,
        "animal_profile.html",
        {
            "principal": principal,
            "household_zone": ZoneInfo(principal.household_timezone),
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "command_id": str(uuid4()),
            "animal": profile,
            "errors": {"form": message},
            "animal_statuses": tuple(sorted(ANIMAL_STATUSES)),
            "enclosures": enclosures,
            "current_enclosure": current_enclosure,
            "recent_events": recent_events[:5],
            "care_actions": _care_action_rows(profile),
            "premolt_status": _premolt_status(profile, animal_service),
            "care_schedules": (
                _care_schedule_rows(
                    principal.household_id,
                    profile,
                    current_enclosure,
                    reminder_projection,
                    principal.household_timezone,
                )
                if reminder_projection is not None
                else ()
            ),
        },
        status_code=422,
    )


def _subject_schedule_rule(
    projection: ReminderProjection,
    household_id: UUID,
    subject_type: str,
    subject_id: UUID,
    reminder_type: str,
) -> ReminderRuleCurrent | None:
    matches = tuple(
        rule
        for rule in projection.rules_for(household_id)
        if rule.subject_type == subject_type
        and rule.subject_id == subject_id
        and rule.reminder_type == reminder_type
    )
    return matches[0] if matches else None


def _care_schedule_rows(
    household_id: UUID,
    animal: Any,
    current_enclosure: Any,
    projection: ReminderProjection,
    timezone_name: str,
    facts: tuple[Any, ...] = (),
    now: datetime | None = None,
) -> tuple[dict[str, Any], ...]:
    timezone = ZoneInfo(timezone_name)
    rows: list[dict[str, Any]] = []
    for reminder_type in animal.reminder_kinds:
        title, subject_type, source_label = CARE_SCHEDULE_CAPABILITIES[reminder_type]
        subject_id = (
            animal.animal_id
            if subject_type == "animal"
            else current_enclosure.enclosure_id
            if current_enclosure is not None
            else None
        )
        rule = (
            _subject_schedule_rule(
                projection,
                household_id,
                subject_type,
                subject_id,
                reminder_type,
            )
            if subject_id is not None
            else None
        )
        fact = next(
            (
                item
                for item in facts
                if item.subject_type == subject_type
                and item.subject_id == subject_id
                and item.reminder_type == reminder_type
            ),
            None,
        )
        rows.append(
            {
                "reminder_type": reminder_type,
                "title": title,
                "interval_label": f"{title} interval",
                "source_label": source_label,
                "available": subject_id is not None,
                "enclosure_name": (
                    current_enclosure.name
                    if subject_type == "enclosure" and current_enclosure
                    else None
                ),
                "enabled": rule.enabled if rule is not None else False,
                "interval_days": rule.interval_days if rule is not None else "",
                "expected_stream_version": rule.stream_version if rule is not None else 0,
                "override_due_at": (
                    rule.override_due_at.astimezone(timezone).strftime("%Y-%m-%dT%H:%M")
                    if rule is not None and rule.override_due_at is not None
                    else ""
                ),
                "due_label": (
                    _friendly_due(
                        fact.due_at,
                        now=now or datetime.now(UTC),
                        timezone=timezone,
                    )
                    if fact is not None
                    else "Next care follows recorded history"
                    if rule is not None and rule.enabled
                    else "Not scheduled"
                ),
                "due_date_label": (
                    fact.due_at.astimezone(timezone).strftime("%b %-d") if fact is not None else ""
                ),
            }
        )
    return tuple(rows)


def _animal_type_options() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "value": profile.animal_type.value,
            "label": profile.label,
            "identity": profile.identity,
        }
        for identity in animal_capability_registry.identities
        for profile in (animal_capability_registry.require(identity),)
    )


def _reminder_subject_rows(
    animals: tuple[Any, ...], enclosures: tuple[Any, ...]
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for animal in animals:
        options = tuple(
            (reminder_type, CARE_SCHEDULE_CAPABILITIES[reminder_type][0])
            for reminder_type in animal.reminder_kinds
            if CARE_SCHEDULE_CAPABILITIES[reminder_type][1] == "animal"
        )
        if options:
            rows.append(
                {
                    "subject": f"animal:{animal.animal_id}",
                    "label": animal.name,
                    "context": animal.type_label,
                    "options": options,
                }
            )
    for enclosure in enclosures:
        occupants = tuple(
            animal for animal in animals if animal.current_enclosure_id == enclosure.enclosure_id
        )
        reminder_types = ["cleaning", "water_change"]
        if any("misting" in animal.reminder_kinds for animal in occupants):
            reminder_types.append("misting")
        rows.append(
            {
                "subject": f"enclosure:{enclosure.enclosure_id}",
                "label": enclosure.name,
                "context": "Enclosure",
                "options": tuple(
                    (reminder_type, CARE_SCHEDULE_CAPABILITIES[reminder_type][0])
                    for reminder_type in reminder_types
                ),
            }
        )
    return tuple(rows)


def _care_action_rows(animal: Any) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "key": key,
            "title": CARE_FORM_DETAILS[key][0],
            "description": CARE_FORM_DETAILS[key][1],
            "href": f"/animals/{animal.animal_id}/{CARE_FORM_DETAILS[key][2]}/new",
        }
        for key in animal.care_action_keys
    )


def _premolt_status(animal: Any, animal_service: AnimalService) -> dict[str, str] | None:
    if not animal.permits(AnimalCapability.PREMOLT):
        return None
    state = animal_service.current_premolt_state(animal.household_id, animal.animal_id)
    return {
        "label": (
            "Observed"
            if state is not None and state.observed
            else "Cleared"
            if state
            else "Not recorded"
        ),
        "observation": state.observation if state is not None and state.observation else "",
    }


CARE_ACTION_LABELS = {
    "feeding": "Feed",
    "weight": "Weigh",
    "length": "Measure",
    "shed": "Record shed",
    "bath": "Record bath",
    "molt": "Record molt",
    "premolt": "Update premolt",
    "misting": "Mist",
    "cleaning": "Clean",
    "water_change": "Change water",
}


def _friendly_due(due_at: datetime, *, now: datetime, timezone: ZoneInfo) -> str:
    days = (due_at.astimezone(timezone).date() - now.astimezone(timezone).date()).days
    if days < -1:
        return f"{-days} days overdue"
    if days == -1:
        return "1 day overdue"
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    if days < 7:
        return f"Due in {days} days"
    return f"Due {due_at.astimezone(timezone).strftime('%b %-d')}"


def _last_care_context(item: Any, timezone: ZoneInfo) -> str:
    if item.source_occurred_at is None:
        return "No qualifying care recorded yet"
    source_label = getattr(item, "source_label", None)
    if not isinstance(source_label, str) or not source_label:
        source_label = CARE_SCHEDULE_CAPABILITIES.get(
            item.reminder_type, ("", "", item.reminder_type)
        )[2]
    label = source_label.replace("accepted feeding", "feeding").replace("last ", "")
    occurred = item.source_occurred_at.astimezone(timezone)
    return f"Last {label} {occurred.strftime('%b %-d')}"


def _agenda_rows(
    items: tuple[Any, ...],
    *,
    animals: tuple[Any, ...],
    enclosures: tuple[Any, ...],
    timezone: ZoneInfo,
    now: datetime,
    return_context: str = "today",
) -> dict[str, tuple[dict[str, Any], ...]]:
    animal_by_id = {animal.animal_id: animal for animal in animals}
    enclosure_by_id = {enclosure.enclosure_id: enclosure for enclosure in enclosures}
    occupants: dict[UUID, list[Any]] = {}
    for animal in animals:
        if animal.current_enclosure_id is not None:
            occupants.setdefault(animal.current_enclosure_id, []).append(animal)
    grouped: dict[str, list[dict[str, Any]]] = {
        "overdue": [],
        "due_today": [],
        "upcoming": [],
    }
    for item in items:
        location_name = None
        action_url = None
        action_label = None
        schedule_url = None
        photo_attachment_version_id = None
        photo_fallback_key = "enclosure"
        if item.subject_type == "animal":
            animal = animal_by_id.get(item.subject_id)
            subject_name = animal.name if animal is not None else "Animal"
            subject_url = f"/animals/{item.subject_id}"
            schedule_url = f"{subject_url}/care"
            photo_attachment_version_id = (
                animal.photo_attachment_version_id if animal is not None else None
            )
            photo_fallback_key = (
                getattr(animal, "animal_type", "animal") if animal is not None else "animal"
            )
            if (
                animal is not None
                and item.reminder_type in animal.care_action_keys
                and item.reminder_type in CARE_FORM_DETAILS
            ):
                title, _description, route = CARE_FORM_DETAILS[item.reminder_type]
                action_url = f"{subject_url}/{route}/new?return_to={return_context}"
                action_label = CARE_ACTION_LABELS.get(item.reminder_type, title)
        else:
            enclosure = enclosure_by_id.get(item.subject_id)
            enclosure_occupants = occupants.get(item.subject_id, [])
            if len(enclosure_occupants) == 1:
                animal = enclosure_occupants[0]
                subject_name = animal.name
                subject_url = f"/animals/{animal.animal_id}"
                schedule_url = f"{subject_url}/care"
                photo_attachment_version_id = animal.photo_attachment_version_id
                photo_fallback_key = getattr(animal, "animal_type", "animal")
                location_name = enclosure.name if enclosure is not None else "Enclosure"
            else:
                subject_name = enclosure.name if enclosure is not None else "Enclosure"
                subject_url = f"/enclosures/{item.subject_id}"
            if item.reminder_type == "misting" and len(enclosure_occupants) == 1:
                animal = enclosure_occupants[0]
                if "misting" in animal.care_action_keys:
                    action_url = (
                        f"/animals/{animal.animal_id}/mistings/new?return_to={return_context}"
                    )
                    action_label = CARE_ACTION_LABELS["misting"]
            elif item.reminder_type in {"cleaning", "water_change"}:
                anchor = "cleaning" if item.reminder_type == "cleaning" else "water-change"
                action_url = f"/enclosures/{item.subject_id}?return_to=today#{anchor}"
                action_label = CARE_ACTION_LABELS[item.reminder_type]
        grouped[item.status].append(
            {
                "item": item,
                "title": CARE_SCHEDULE_CAPABILITIES.get(
                    item.reminder_type,
                    (item.reminder_type.replace("_", " ").title(), "", ""),
                )[0],
                "subject_name": subject_name,
                "subject_url": subject_url,
                "location_name": location_name,
                "action_url": action_url,
                "action_label": action_label,
                "schedule_url": schedule_url,
                "photo_attachment_version_id": photo_attachment_version_id,
                "photo_fallback_key": photo_fallback_key,
                "due_label": _friendly_due(item.due_at, now=now, timezone=timezone),
                "last_context": _last_care_context(item, timezone),
                "explanation": item.explanation,
            }
        )
    return {key: tuple(value) for key, value in grouped.items()}


def _animal_collection_rows(
    animals: tuple[Any, ...],
    items: tuple[Any, ...],
    *,
    enclosures: tuple[Any, ...],
    timezone: ZoneInfo,
    now: datetime,
) -> tuple[dict[str, Any], ...]:
    enclosure_names = {item.enclosure_id: item.name for item in enclosures}
    status_order = {"overdue": 0, "due_today": 1, "upcoming": 2}
    by_animal: dict[UUID, list[Any]] = {}
    animals_by_enclosure: dict[UUID, list[Any]] = {}
    for animal in animals:
        if animal.current_enclosure_id is not None:
            animals_by_enclosure.setdefault(animal.current_enclosure_id, []).append(animal)
    for item in items:
        if item.subject_type == "animal":
            by_animal.setdefault(item.subject_id, []).append(item)
        elif item.subject_type == "enclosure":
            for animal in animals_by_enclosure.get(item.subject_id, []):
                by_animal.setdefault(animal.animal_id, []).append(item)
    rows = []
    for animal in animals:
        next_item = min(
            by_animal.get(animal.animal_id, ()),
            key=lambda item: (status_order[item.status], item.due_at, item.rule_id),
            default=None,
        )
        rows.append(
            {
                "animal": animal,
                "enclosure_name": enclosure_names.get(animal.current_enclosure_id),
                "care_label": (
                    f"{CARE_SCHEDULE_CAPABILITIES[next_item.reminder_type][0]} · "
                    f"{_friendly_due(next_item.due_at, now=now, timezone=timezone)}"
                    if next_item is not None
                    else "No care scheduled"
                ),
                "care_status": next_item.status if next_item is not None else "none",
            }
        )
    return tuple(rows)


def _enclosure_collection_rows(
    enclosures: tuple[Any, ...],
    animals: tuple[Any, ...],
    items: tuple[Any, ...],
    *,
    timezone: ZoneInfo,
    now: datetime,
) -> tuple[dict[str, Any], ...]:
    status_order = {"overdue": 0, "due_today": 1, "upcoming": 2}
    by_enclosure: dict[UUID, list[Any]] = {}
    occupants: dict[UUID, list[Any]] = {}
    for animal in animals:
        if animal.current_enclosure_id is not None:
            occupants.setdefault(animal.current_enclosure_id, []).append(animal)
    for item in items:
        if item.subject_type == "enclosure":
            by_enclosure.setdefault(item.subject_id, []).append(item)
    rows = []
    for enclosure in enclosures:
        next_item = min(
            by_enclosure.get(enclosure.enclosure_id, ()),
            key=lambda item: (status_order[item.status], item.due_at, item.rule_id),
            default=None,
        )
        rows.append(
            {
                "enclosure": enclosure,
                "occupants": tuple(occupants.get(enclosure.enclosure_id, ())),
                "maintenance_label": (
                    f"{CARE_SCHEDULE_CAPABILITIES[next_item.reminder_type][0]} · "
                    f"{_friendly_due(next_item.due_at, now=now, timezone=timezone)}"
                    if next_item is not None
                    else "No care due"
                ),
                "maintenance_status": next_item.status if next_item is not None else "none",
            }
        )
    return tuple(rows)


def _completed_care_rows(
    *,
    household_id: UUID,
    animals: tuple[Any, ...],
    enclosures: tuple[Any, ...],
    animal_service: AnimalService,
    enclosure_service: EnclosureService,
    timezone: ZoneInfo,
) -> tuple[dict[str, Any], ...]:
    animal_by_id = {animal.animal_id: animal for animal in animals}
    enclosure_by_id = {enclosure.enclosure_id: enclosure for enclosure in enclosures}
    events: dict[UUID, DomainEvent] = {}
    for animal in animals:
        for event in animal_service.effective_history(household_id, animal.animal_id):
            if event.event_type in RECENT_CARE_EVENT_TYPES:
                events[event.event_id] = event
    for enclosure in enclosures:
        for event in enclosure_service.effective_history(household_id, enclosure.enclosure_id):
            if event.event_type in RECENT_CARE_EVENT_TYPES:
                events[event.event_id] = event
    presented = present_effective_care_events(
        tuple(events.values()),
        enclosure_names={item.enclosure_id: item.name for item in enclosures},
    )
    rows = []
    for view in presented:
        event = view.event
        animal = animal_by_id.get(event.stream_id) if event.stream_type == "animal" else None
        enclosure = (
            enclosure_by_id.get(event.stream_id) if event.stream_type == "enclosure" else None
        )
        occurred = event.occurred_at.astimezone(timezone)
        rows.append(
            {
                "event": event,
                "title": view.title,
                "description": view.description,
                "subject_name": animal.name if animal else enclosure.name if enclosure else "Care",
                "subject_url": (
                    f"/animals/{animal.animal_id}"
                    if animal
                    else f"/enclosures/{enclosure.enclosure_id}"
                    if enclosure
                    else "/home"
                ),
                "photo_attachment_version_id": (
                    animal.photo_attachment_version_id if animal else None
                ),
                "local_date": occurred.date(),
                "occurred_label": occurred.strftime("%b %-d · %-I:%M %p"),
            }
        )
    return tuple(rows)


def _month_date(value: str, fallback: date) -> date:
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError:
        return fallback.replace(day=1)
    return parsed


def _calendar_view(
    *,
    month_value: str,
    selected_value: str,
    scheduled_rows: tuple[dict[str, Any], ...],
    completed: tuple[dict[str, Any], ...],
    timezone: ZoneInfo,
    now: datetime,
) -> dict[str, Any]:
    today = now.astimezone(timezone).date()
    month_start = _month_date(month_value, today)
    try:
        selected_date = date.fromisoformat(selected_value) if selected_value else today
    except ValueError:
        selected_date = today
    scheduled_by_date: dict[date, list[Any]] = {}
    for row in scheduled_rows:
        scheduled_by_date.setdefault(row["item"].due_at.astimezone(timezone).date(), []).append(row)
    completed_by_date: dict[date, list[dict[str, Any]]] = {}
    for row in completed:
        completed_by_date.setdefault(row["local_date"], []).append(row)
    weeks = []
    for week in Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month):
        weeks.append(
            tuple(
                {
                    "date": day,
                    "in_month": day.month == month_start.month,
                    "is_today": day == today,
                    "is_selected": day == selected_date,
                    "scheduled_count": len(scheduled_by_date.get(day, ())),
                    "overdue_count": sum(
                        1
                        for row in scheduled_by_date.get(day, ())
                        if row["item"].status == "overdue"
                    ),
                    "due_count": sum(
                        1
                        for row in scheduled_by_date.get(day, ())
                        if row["item"].status == "due_today"
                    ),
                    "upcoming_count": sum(
                        1
                        for row in scheduled_by_date.get(day, ())
                        if row["item"].status == "upcoming"
                    ),
                    "completed_count": len(completed_by_date.get(day, ())),
                }
                for day in week
            )
        )
    previous_month = month_start - timedelta(days=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {
        "today": today,
        "month_start": month_start,
        "month_label": month_start.strftime("%B %Y"),
        "month_value": month_start.strftime("%Y-%m"),
        "previous_month": previous_month.strftime("%Y-%m"),
        "next_month": next_month.strftime("%Y-%m"),
        "weeks": tuple(weeks),
        "selected_date": selected_date,
        "selected_scheduled": tuple(scheduled_by_date.get(selected_date, ())),
        "selected_completed": tuple(completed_by_date.get(selected_date, ())),
        "scheduled_dates": tuple(
            (day, tuple(rows)) for day, rows in sorted(scheduled_by_date.items())
        ),
        "recent_completed": completed[:12],
    }


def _animal_edit_error(
    request: Request,
    principal: Principal,
    animal_id: str,
    message: str,
    animal_service: AnimalService,
) -> HTMLResponse:
    try:
        animal = animal_service.profile_for(principal.household_id, UUID(animal_id))
    except ValueError:
        animal = None
    if animal is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"title": "Animal not found", "message": "Return to your animal list and try again."},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "animal_edit.html",
        {
            "principal": principal,
            "household_zone": ZoneInfo(principal.household_timezone),
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "command_id": str(uuid4()),
            "animal": animal,
            "errors": {"form": message},
        },
        status_code=422,
    )


def _animal_timeline_error(
    request: Request,
    principal: Principal,
    animal_id: str,
    message: str,
    animal_service: AnimalService,
    enclosure_service: EnclosureService,
) -> HTMLResponse:
    try:
        animal_uuid = UUID(animal_id)
        animal = animal_service.profile_for(principal.household_id, animal_uuid)
    except ValueError:
        animal = None
        animal_uuid = None
    if animal is None or animal_uuid is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"title": "Animal not found", "message": "Return to your animal list and try again."},
            status_code=404,
        )
    context = _timeline_context(
        animal_service, enclosure_service, principal.household_id, animal_uuid
    )
    context["animal"] = animal
    context["errors"] = {"form": message}
    return templates.TemplateResponse(
        request,
        "animal_timeline.html",
        {
            "principal": principal,
            "household_zone": ZoneInfo(principal.household_timezone),
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "command_id": str(uuid4()),
            **context,
        },
        status_code=422,
    )


def _enclosure_form_error(
    request: Request,
    principal: Principal,
    enclosure_id: str,
    message: str,
    enclosure_service: EnclosureService,
) -> HTMLResponse:
    try:
        enclosure = enclosure_service.profile_for(principal.household_id, UUID(enclosure_id))
    except ValueError:
        enclosure = None
    if enclosure is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": "Enclosure not found",
                "message": "Return to your household workspace and try again.",
            },
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "enclosure_profile.html",
        {
            "principal": principal,
            "household_zone": ZoneInfo(principal.household_timezone),
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "command_id": str(uuid4()),
            "enclosure": enclosure,
            "occupants": enclosure_service.occupants(
                principal.household_id, enclosure.enclosure_id
            ),
            "enclosure_statuses": tuple(sorted(ENCLOSURE_STATUSES)),
            "errors": {"form": message},
        },
        status_code=422,
    )


def _enclosure_edit_error(
    request: Request,
    principal: Principal,
    enclosure_id: str,
    message: str,
    enclosure_service: EnclosureService,
) -> HTMLResponse:
    try:
        enclosure = enclosure_service.profile_for(principal.household_id, UUID(enclosure_id))
    except ValueError:
        enclosure = None
    if enclosure is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": "Enclosure not found",
                "message": "Return to your enclosure list and try again.",
            },
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "enclosure_edit.html",
        {
            "principal": principal,
            "household_zone": ZoneInfo(principal.household_timezone),
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "command_id": str(uuid4()),
            "enclosure": enclosure,
            "errors": {"form": message},
        },
        status_code=422,
    )


def _animal_history_page(
    request: Request,
    animal_id: str,
    *,
    principal_for: Callable[..., Principal | None],
    protected_page: Callable[..., HTMLResponse],
    animal_service: AnimalService,
    enclosure_service: EnclosureService,
    event_types: frozenset[str],
    page_title: str,
    page_description: str,
    empty_message: str,
) -> Response:
    principal = principal_for(request, audit_denial=True)
    if principal is None:
        return RedirectResponse("/login", status_code=303)
    try:
        animal_uuid = UUID(animal_id)
        animal = animal_service.profile_for(principal.household_id, animal_uuid)
    except ValueError:
        animal = None
        animal_uuid = None
    if animal is None or animal_uuid is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": "Animal not found",
                "message": "Return to your animal list and try again.",
            },
            status_code=404,
        )
    context = _timeline_context(
        animal_service, enclosure_service, principal.household_id, animal_uuid
    )
    context["events"] = tuple(
        event for event in context["events"] if event.event.event_type in event_types
    )
    return protected_page(
        request,
        "animal_timeline.html",
        principal,
        context={
            "animal": animal,
            "page_title": page_title,
            "page_description": page_description,
            "empty_message": empty_message,
            **context,
        },
    )


def _animal_care_form_page(
    request: Request,
    animal_id: str,
    care_kind: str,
    *,
    principal: Principal,
    protected_page: Callable[..., HTMLResponse],
    animal_service: AnimalService,
    inventory_service: InventoryService,
    status_code: int = 200,
    error: str | None = None,
    values: dict[str, str] | None = None,
) -> Response:
    try:
        animal = animal_service.profile_for(principal.household_id, UUID(animal_id))
    except ValueError:
        animal = None
    if animal is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": "Animal not found",
                "message": "Return to your animal list and try again.",
            },
            status_code=404,
        )
    if care_kind not in animal.care_action_keys:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": "Care action not available",
                "message": (
                    f"{care_kind.replace('_', ' ').title()} care is not available "
                    f"for the {animal.type_label} profile."
                ),
            },
            status_code=422,
        )
    title, description, route = CARE_FORM_DETAILS[care_kind]
    form_values = values or {}
    return_context = _care_return_context(
        form_values.get("return_to", request.query_params.get("return_to", "animal"))
    )
    return protected_page(
        request,
        "animal_care_form.html",
        principal,
        status_code=status_code,
        context={
            "animal": animal,
            "care_kind": care_kind,
            "page_title": title,
            "page_description": description,
            "action": f"/animals/{animal_id}/{route}",
            "errors": {"form": error} if error else {},
            "values": form_values,
            "inventory_items": inventory_service.list_balances(principal.household_id),
            "return_context": return_context,
            "return_url": _care_return_location(animal_id, return_context),
        },
    )
