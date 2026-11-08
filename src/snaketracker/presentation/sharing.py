"""Authenticated album controls and deliberately limited visitor presentations."""

from __future__ import annotations

from contextlib import suppress
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, UploadFile
from starlette.exceptions import HTTPException

from snaketracker.application.animals import AnimalService
from snaketracker.application.attachments import MAX_PROFILE_PHOTO_BYTES, AttachmentValidationError
from snaketracker.application.identity import AuthenticationError, IdentityService, Principal
from snaketracker.application.sharing import (
    SharingAuthorizationError,
    SharingService,
    SharingValidationError,
)
from snaketracker.platform.events.store import (
    ExpectedVersionConflictError,
    IdempotencyConflictError,
)
from snaketracker.presentation.sharing_guard import NO_STORE
from snaketracker.presentation.web import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    _client_context,
    _form_request_valid,
    _set_session_cookies,
    templates,
)

MAX_FORM_BYTES = MAX_PROFILE_PHOTO_BYTES + 64 * 1024


async def _bounded_form(request: Request, *, upload: bool = False) -> FormData:
    """Enforce the whole body bound, including streamed/chunked multipart files."""
    maximum = MAX_FORM_BYTES if upload else 32 * 1024
    try:
        length = int(request.headers.get("content-length", "0"))
    except ValueError as error:
        raise HTTPException(400, "Invalid form length") from error
    if length < 0 or length > maximum:
        raise HTTPException(413, "The upload is too large. Choose a photo up to 20 MiB.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > maximum:
            raise HTTPException(413, "The upload is too large. Choose a photo up to 20 MiB.")
        body.extend(chunk)
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    bounded = Request(request.scope, receive)
    return await bounded.form(max_files=1 if upload else 0, max_fields=16, max_part_size=4096)


def create_sharing_router(
    *,
    sharing: SharingService,
    animals: AnimalService,
    identity: IdentityService,
    secure_cookie: bool,
    expected_origin: str | None,
    public_enabled: bool,
) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    def access(request: Request, *, mutate: bool = False) -> Principal | Response:
        token = request.cookies.get(SESSION_COOKIE)
        principal = None
        if token:
            with suppress(AuthenticationError):
                principal = identity.authenticate(token)
        if principal is None:
            return RedirectResponse("/login", status_code=303, headers=NO_STORE)
        if mutate and "household.manage" not in principal.capabilities:
            return PlainTextResponse("Access denied", status_code=403, headers=NO_STORE)
        return principal

    def not_found() -> Response:
        return PlainTextResponse("Not found", status_code=404, headers=NO_STORE)

    def conflict() -> Response:
        return PlainTextResponse(
            "These choices changed while you were editing. "
            "Return to the form, reload and try again.",
            status_code=409,
            headers=NO_STORE,
        )

    def page(
        request: Request,
        template: str,
        principal: Principal,
        *,
        status_code: int = 200,
        **context: object,
    ) -> HTMLResponse:
        csrf = request.cookies.get(CSRF_COOKIE)
        issued = None
        if not csrf:
            client_ip, user_agent = _client_context(request)
            issued = identity.rotate_session(
                request.cookies[SESSION_COOKIE],
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=uuid4(),
            )
            csrf = issued.csrf_token
        response = templates.TemplateResponse(
            request,
            template,
            {
                "principal": principal,
                "csrf_token": csrf,
                "command_id": str(uuid4()),
                "can_manage": (
                    "household.manage" in principal.capabilities
                    and getattr(context.get("animal"), "status", "active") == "active"
                ),
                "public_enabled": public_enabled,
                "error": None,
                "values": {},
                **context,
            },
            status_code=status_code,
            headers=NO_STORE,
        )
        if issued:
            _set_session_cookies(response, issued, secure_cookie)
        return response

    async def submission(
        request: Request, *, upload: bool = False
    ) -> tuple[Principal | None, FormData | None, Response | None]:
        principal = access(request, mutate=True)
        if isinstance(principal, Response):
            return None, None, principal
        if not _form_request_valid(request, expected_origin):
            return None, None, PlainTextResponse("Request could not be verified", 403, NO_STORE)
        try:
            form = await _bounded_form(request, upload=upload)
        except HTTPException as error:
            return None, None, PlainTextResponse(str(error.detail), error.status_code, NO_STORE)
        if not identity.verify_csrf(
            request.cookies[SESSION_COOKIE], str(form.get("csrf_token", ""))
        ):
            await form.close()
            return None, None, PlainTextResponse("Request could not be verified", 403, NO_STORE)
        return principal, form, None

    def command_key(form: FormData) -> str:
        key = str(form.get("idempotency_key", ""))
        if not key or len(key) > 120:
            raise SharingValidationError("Refresh this form and try again.")
        return key

    def animal_for(principal: Principal, animal_id: str) -> Any:
        try:
            return animals.profile_for(principal.household_id, UUID(animal_id))
        except ValueError:
            return None

    def owner_animals(principal: Principal) -> list[dict[str, Any]]:
        return [
            {"animal": animal, "publication": sharing.animal(principal, animal.animal_id)}
            for animal in animals.list_profiles(principal.household_id)
            if animal.status == "active"
        ]

    @router.get("/sharing", response_class=HTMLResponse)
    def collection_settings(request: Request) -> Response:
        principal = access(request)
        if isinstance(principal, Response):
            return principal
        return page(
            request,
            "sharing_collection_settings.html",
            principal,
            publication=sharing.household(principal),
            animals=owner_animals(principal),
        )

    @router.post("/sharing", response_class=HTMLResponse)
    async def collection_save(request: Request) -> Response:
        principal, form, denial = await submission(request)
        if denial:
            return denial
        assert principal and form is not None
        try:
            sharing.configure_household(
                principal,
                enabled=form.get("enabled") == "true",
                title=str(form.get("title", "")),
                description=str(form.get("description", "")),
                slug=str(form.get("slug", "")),
                idempotency_key=command_key(form),
            )
        except (SharingValidationError, ValueError) as error:
            return page(
                request,
                "sharing_collection_settings.html",
                principal,
                status_code=422,
                publication=sharing.household(principal),
                animals=owner_animals(principal),
                values=dict(form),
                error=str(error),
            )
        except SharingAuthorizationError:
            return not_found()
        except (ExpectedVersionConflictError, IdempotencyConflictError):
            return conflict()
        finally:
            await form.close()
        return RedirectResponse("/sharing?saved=1", 303, headers=NO_STORE)

    @router.get("/animals/{animal_id}/album", response_class=HTMLResponse)
    def album(request: Request, animal_id: str) -> Response:
        principal = access(request)
        if isinstance(principal, Response):
            return principal
        animal = animal_for(principal, animal_id)
        if animal is None:
            return not_found()
        return page(
            request,
            "animal_album.html",
            principal,
            animal=animal,
            photos=sharing.photos(principal, animal.animal_id),
        )

    @router.post("/animals/{animal_id}/album/upload", response_class=HTMLResponse)
    async def upload_photo(request: Request, animal_id: str) -> Response:
        principal, form, denial = await submission(request, upload=True)
        if denial:
            return denial
        assert principal and form is not None
        animal = animal_for(principal, animal_id)
        if animal is None:
            await form.close()
            return not_found()
        try:
            photo = form.get("photo")
            if not isinstance(photo, UploadFile):
                raise SharingValidationError("Choose a JPEG, PNG or WebP photo.")
            content = await photo.read(MAX_PROFILE_PHOTO_BYTES + 1)
            await run_in_threadpool(
                sharing.upload_photo,
                principal,
                animal.animal_id,
                content=content,
                declared_media_type=photo.content_type or "application/octet-stream",
                caption=str(form.get("caption", "")),
                idempotency_key=command_key(form),
            )
        except (SharingValidationError, AttachmentValidationError, ValueError) as error:
            return page(
                request,
                "animal_album.html",
                principal,
                status_code=422,
                animal=animal,
                photos=sharing.photos(principal, animal.animal_id),
                values={"caption": str(form.get("caption", ""))},
                error=str(error),
            )
        except SharingAuthorizationError:
            return not_found()
        except (ExpectedVersionConflictError, IdempotencyConflictError):
            return conflict()
        finally:
            await form.close()
        return RedirectResponse(f"/animals/{animal_id}/album?uploaded=1", 303, headers=NO_STORE)

    @router.get("/animals/{animal_id}/album/{media_id}", response_class=HTMLResponse)
    def photo_edit(request: Request, animal_id: str, media_id: str) -> Response:
        principal = access(request)
        if isinstance(principal, Response):
            return principal
        animal = animal_for(principal, animal_id)
        if animal is None:
            return not_found()
        photo = next(
            (p for p in sharing.photos(principal, animal.animal_id) if str(p.media_id) == media_id),
            None,
        )
        if photo is None:
            return not_found()
        return page(request, "album_photo_edit.html", principal, animal=animal, photo=photo)

    @router.post("/animals/{animal_id}/album/{media_id}", response_class=HTMLResponse)
    async def photo_save(request: Request, animal_id: str, media_id: str) -> Response:
        principal, form, denial = await submission(request)
        if denial:
            return denial
        assert principal and form is not None
        animal = animal_for(principal, animal_id)
        if animal is None:
            await form.close()
            return not_found()
        photo = next(
            (p for p in sharing.photos(principal, animal.animal_id) if str(p.media_id) == media_id),
            None,
        )
        if photo is None:
            await form.close()
            return not_found()
        try:
            sharing.update_photo(
                principal,
                animal.animal_id,
                UUID(media_id),
                caption=str(form.get("caption", "")),
                position=int(str(form.get("position", "1"))),
                is_public=form.get("is_public") == "true",
                idempotency_key=command_key(form),
            )
        except (SharingValidationError, ValueError) as error:
            return page(
                request,
                "album_photo_edit.html",
                principal,
                status_code=422,
                animal=animal,
                photo=photo,
                values=dict(form),
                error=str(error),
            )
        except SharingAuthorizationError:
            return not_found()
        except (ExpectedVersionConflictError, IdempotencyConflictError):
            return conflict()
        finally:
            await form.close()
        return RedirectResponse(f"/animals/{animal_id}/album?saved=1", 303, headers=NO_STORE)

    @router.post("/animals/{animal_id}/album/{media_id}/remove", response_class=HTMLResponse)
    async def photo_remove(request: Request, animal_id: str, media_id: str) -> Response:
        principal, form, denial = await submission(request)
        if denial:
            return denial
        assert principal and form is not None
        try:
            sharing.remove_photo(
                principal, UUID(animal_id), UUID(media_id), idempotency_key=command_key(form)
            )
        except (SharingAuthorizationError, SharingValidationError, ValueError):
            return not_found()
        except (ExpectedVersionConflictError, IdempotencyConflictError):
            return conflict()
        finally:
            await form.close()
        return RedirectResponse(f"/animals/{animal_id}/album?removed=1", 303, headers=NO_STORE)

    @router.api_route("/animals/{animal_id}/album/{media_id}/photo", methods=["GET", "HEAD"])
    def private_photo(request: Request, animal_id: str, media_id: str) -> Response:
        principal = access(request)
        if isinstance(principal, Response):
            return principal
        try:
            delivered = sharing.private_photo(principal, UUID(animal_id), UUID(media_id))
        except (
            SharingAuthorizationError,
            SharingValidationError,
            AttachmentValidationError,
            ValueError,
        ):
            return not_found()
        return Response(
            b"" if request.method == "HEAD" else delivered.content,
            media_type=delivered.finalized.metadata.media_type,
            headers={**NO_STORE, "Content-Disposition": 'inline; filename="album-photo"'},
        )

    @router.get("/animals/{animal_id}/sharing", response_class=HTMLResponse)
    def animal_settings(request: Request, animal_id: str) -> Response:
        principal = access(request)
        if isinstance(principal, Response):
            return principal
        animal = animal_for(principal, animal_id)
        if animal is None:
            return not_found()
        return page(
            request,
            "animal_sharing.html",
            principal,
            animal=animal,
            publication=sharing.animal(principal, animal.animal_id),
            collection=sharing.household(principal),
            photos=sharing.photos(principal, animal.animal_id),
        )

    @router.post("/animals/{animal_id}/sharing", response_class=HTMLResponse)
    async def animal_save(request: Request, animal_id: str) -> Response:
        principal, form, denial = await submission(request)
        if denial:
            return denial
        assert principal and form is not None
        animal = animal_for(principal, animal_id)
        if animal is None:
            await form.close()
            return not_found()
        try:
            cover = str(form.get("cover_media_id", ""))
            sharing.configure_animal(
                principal,
                animal.animal_id,
                is_public=form.get("is_public") == "true",
                title=str(form.get("title", "")),
                species=str(form.get("species", "")),
                description=str(form.get("description", "")),
                slug=str(form.get("slug", "")),
                cover_media_id=UUID(cover) if cover else None,
                idempotency_key=command_key(form),
            )
        except (SharingValidationError, ValueError) as error:
            return page(
                request,
                "animal_sharing.html",
                principal,
                status_code=422,
                animal=animal,
                publication=sharing.animal(principal, animal.animal_id),
                collection=sharing.household(principal),
                photos=sharing.photos(principal, animal.animal_id),
                values=dict(form),
                error=str(error),
            )
        except SharingAuthorizationError:
            return not_found()
        except (ExpectedVersionConflictError, IdempotencyConflictError):
            return conflict()
        finally:
            await form.close()
        return RedirectResponse(f"/animals/{animal_id}/sharing?saved=1", 303, headers=NO_STORE)

    @router.get("/animals/{animal_id}/sharing/preview", response_class=HTMLResponse)
    def animal_preview(request: Request, animal_id: str) -> Response:
        principal = access(request)
        if isinstance(principal, Response):
            return principal
        animal = animal_for(principal, animal_id)
        if animal is None:
            return not_found()
        published = sharing.preview_animal(principal, animal.animal_id)
        if published is None:
            return RedirectResponse(f"/animals/{animal_id}/sharing", 303, headers=NO_STORE)
        photo_paths = {
            photo.public_token: f"/animals/{animal_id}/album/{photo.media_id}/photo"
            for photo in sharing.photos(principal, animal.animal_id)
        }
        return templates.TemplateResponse(
            request,
            "public_animal.html",
            {
                "profile": published,
                "preview": True,
                "preview_back": f"/animals/{animal_id}/sharing",
                "photo_paths": photo_paths,
                "collection_path": "/sharing/preview",
            },
            headers=NO_STORE,
        )

    @router.get("/sharing/preview", response_class=HTMLResponse)
    def collection_preview(request: Request) -> Response:
        principal = access(request)
        if isinstance(principal, Response):
            return principal
        collection = sharing.preview_collection(principal)
        if collection is None:
            return RedirectResponse("/sharing", 303, headers=NO_STORE)
        animal_paths, photo_paths = {}, {}
        for row in owner_animals(principal):
            animal, publication = row["animal"], row["publication"]
            if publication is not None:
                animal_paths[publication.slug] = f"/animals/{animal.animal_id}/sharing/preview"
                for photo in sharing.photos(principal, animal.animal_id):
                    photo_paths[photo.public_token] = (
                        f"/animals/{animal.animal_id}/album/{photo.media_id}/photo"
                    )
        return templates.TemplateResponse(
            request,
            "public_collection.html",
            {
                "collection": collection,
                "preview": True,
                "preview_back": "/sharing",
                "animal_paths": animal_paths,
                "photo_paths": photo_paths,
            },
            headers=NO_STORE,
        )

    @router.api_route("/p/{slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def public_animal(request: Request, slug: str) -> Response:
        if not public_enabled:
            return not_found()
        profile = sharing.public_animal(slug)
        if profile is None:
            return not_found()
        return templates.TemplateResponse(
            request,
            "public_animal.html",
            {"profile": profile, "preview": False, "photo_paths": {}, "collection_path": None},
            headers=NO_STORE,
        )

    @router.api_route("/c/{slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def public_collection(request: Request, slug: str) -> Response:
        if not public_enabled:
            return not_found()
        collection = sharing.public_collection(slug)
        if collection is None:
            return not_found()
        return templates.TemplateResponse(
            request,
            "public_collection.html",
            {"collection": collection, "preview": False, "photo_paths": {}, "animal_paths": {}},
            headers=NO_STORE,
        )

    @router.api_route("/m/{token}", methods=["GET", "HEAD"])
    def public_photo(request: Request, token: str) -> Response:
        if not public_enabled:
            return not_found()
        try:
            delivered = sharing.public_photo(token)
        except AttachmentValidationError:
            return not_found()
        if delivered is None:
            return not_found()
        return Response(
            b"" if request.method == "HEAD" else delivered.content,
            media_type=delivered.finalized.metadata.media_type,
            headers={**NO_STORE, "Content-Disposition": 'inline; filename="shared-photo"'},
        )

    return router
