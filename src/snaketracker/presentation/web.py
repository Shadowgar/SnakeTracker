"""Server-rendered identity and household browser experience."""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from snaketracker.application.animals import (
    AnimalService,
    AnimalValidationError,
    AssignEnclosureCommand,
    ChangeAnimalStatusCommand,
    CorrectFeedingCommand,
    CorrectLengthCommand,
    CorrectShedCommand,
    CorrectWeightCommand,
    RecordBathCommand,
    RecordFeedingCommand,
    RecordLengthCommand,
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
from snaketracker.application.enclosures import (
    ChangeEnclosureStatusCommand,
    EnclosureService,
    EnclosureValidationError,
    RecordCleaningCommand,
    RecordWaterChangeCommand,
    RegisterEnclosureCommand,
    UpdateEnclosureProfileCommand,
)
from snaketracker.application.household_bootstrap import (
    AlreadyBootstrappedError,
    BootstrapCommand,
    BootstrapConflictError,
    BootstrapValidationError,
    HouseholdBootstrapService,
)
from snaketracker.application.identity import (
    AuthenticationError,
    IdentityService,
    LoginBlockedError,
    Principal,
)
from snaketracker.domains.animals.contracts import ANIMAL_STATUSES
from snaketracker.domains.enclosures.contracts import ENCLOSURE_STATUSES
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.registry import production_event_registry
from snaketracker.platform.events.validation import household_local_to_utc
from snaketracker.presentation.animal_care_views import (
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
}


class FormValidationError(ValueError):
    """A browser form value cannot be converted to an owned command input."""


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
        if capabilities.voidable and event.event_id not in active_voids:
            voidable.add(event.event_id)
        if capabilities.reinstatable and event.event_id in active_voids:
            reinstatable.add(event.event_id)
    return {
        "correctable_event_ids": frozenset(correctable),
        "voidable_event_ids": frozenset(voidable),
        "reinstatable_event_ids": frozenset(reinstatable),
    }


def _timeline_context(
    animal_service: AnimalService, household_id: UUID, animal_id: UUID
) -> dict[str, Any]:
    audit_events = animal_service.audit_history(household_id, animal_id)
    return {
        "events": present_effective_care_events(
            animal_service.effective_history(household_id, animal_id)
        ),
        "audit_events": present_care_events(audit_events),
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
    csrf_token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        request,
        template,
        {"csrf_token": csrf_token, "errors": {}, "values": {}, **(context or {})},
        status_code=status_code,
    )
    _set_cookie(response, CSRF_COOKIE, csrf_token, secure_cookie)
    return response


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
    identity_service: IdentityService,
    animal_service: AnimalService,
    attachment_service: AttachmentService,
    backup_service: BackupService,
    enclosure_service: EnclosureService,
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
        return _new_form_response(request, "login.html", secure_cookie=secure_cookie)

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
        response = templates.TemplateResponse(
            request,
            "home.html",
            {
                "principal": principal,
                "csrf_token": csrf_token,
                "animals": animal_service.list_profiles(principal.household_id),
            },
        )
        if issued is not None:
            _set_cookie(response, SESSION_COOKIE, issued.token, secure_cookie)
            _set_cookie(response, CSRF_COOKIE, issued.csrf_token, secure_cookie)
        return response

    @router.get("/animals", response_class=HTMLResponse)
    async def animal_list(request: Request) -> Response:
        return await home(request)

    @router.get("/enclosures", response_class=HTMLResponse)
    async def enclosure_list(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return protected_page(
            request,
            "enclosure_list.html",
            principal,
            context={"enclosures": enclosure_service.list_profiles(principal.household_id)},
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

    @router.get("/animals/new", response_class=HTMLResponse)
    async def animal_new(request: Request) -> Response:
        principal = principal_for(request, audit_denial=True)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return protected_page(
            request,
            "animal_new.html",
            principal,
            context={"errors": {}, "values": {}},
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
        return RedirectResponse(f"/enclosures/{enclosure_id}", status_code=303)

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
        return RedirectResponse(f"/enclosures/{enclosure_id}", status_code=303)

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
                context={"errors": {"form": str(error)}, "values": values},
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
        enclosures = enclosure_service.list_profiles(principal.household_id)
        current_enclosure = next(
            (
                enclosure
                for enclosure in enclosures
                if enclosure.enclosure_id == profile.current_enclosure_id
            ),
            None,
        )
        recent_events = present_effective_care_events(
            animal_service.effective_history(principal.household_id, profile.animal_id)
        )
        return protected_page(
            request,
            "animal_profile.html",
            principal,
            context={
                "animal": profile,
                "enclosures": enclosures,
                "current_enclosure": current_enclosure,
                "recent_events": recent_events[:5],
                "animal_statuses": tuple(sorted(ANIMAL_STATUSES)),
            },
        )

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
            return _animal_form_error(
                request,
                principal,
                animal_id,
                str(error),
                animal_service,
                enclosure_service,
            )
        finally:
            if isinstance(upload, UploadFile):
                await upload.close()
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
            return _animal_form_error(
                request, principal, animal_id, str(error), animal_service, enclosure_service
            )
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
            return _animal_form_error(
                request,
                principal,
                animal_id,
                str(error),
                animal_service,
                enclosure_service,
            )
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
        return RedirectResponse(f"/animals/{animal_id}", status_code=303)

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
            return _animal_timeline_error(request, principal, animal_id, str(error), animal_service)
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
            return _animal_timeline_error(request, principal, animal_id, str(error), animal_service)
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
                "animal": profile,
                **_timeline_context(animal_service, principal.household_id, animal_uuid),
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
    recent_events = present_effective_care_events(
        animal_service.effective_history(principal.household_id, profile.animal_id)
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
        },
        status_code=422,
    )


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
    context = _timeline_context(animal_service, principal.household_id, animal_uuid)
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
    context = _timeline_context(animal_service, principal.household_id, animal_uuid)
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
    title, description, route = CARE_FORM_DETAILS[care_kind]
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
            "values": values or {},
        },
    )
