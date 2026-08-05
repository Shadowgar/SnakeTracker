"""Server-rendered identity and household browser experience."""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from snaketracker.application.household_bootstrap import (
    AlreadyBootstrappedError,
    BootstrapCommand,
    BootstrapConflictError,
    HouseholdBootstrapService,
)
from snaketracker.application.identity import (
    AuthenticationError,
    IdentityService,
    LoginBlockedError,
    Principal,
)

SESSION_COOKIE = "snaketracker_session"
CSRF_COOKIE = "snaketracker_csrf"
PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")


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


def create_web_router(
    *,
    bootstrap_service: HouseholdBootstrapService,
    identity_service: IdentityService,
    is_bootstrapped: Callable[[], bool],
    secure_cookie: bool,
) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    def principal_for(request: Request) -> Principal | None:
        token = request.cookies.get(SESSION_COOKIE)
        if token is None:
            return None
        try:
            return identity_service.authenticate(token)
        except AuthenticationError:
            return None

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
        except ValueError as error:
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
        principal = principal_for(request)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        return templates.TemplateResponse(
            request,
            "home.html",
            {"principal": principal, "csrf_token": request.cookies.get(CSRF_COOKIE, "")},
        )

    @router.post("/logout")
    async def logout(request: Request) -> Response:
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
