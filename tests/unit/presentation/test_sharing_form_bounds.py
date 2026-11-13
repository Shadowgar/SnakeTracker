"""Chunked requests cannot evade M9's bounded upload parser."""

import pytest
from starlette.exceptions import HTTPException
from starlette.requests import Request

from snaketracker.presentation.sharing import MAX_FORM_BYTES, _bounded_form


@pytest.mark.anyio
async def test_chunked_upload_stops_before_unbounded_multipart_parsing():
    calls = 0

    async def receive():
        nonlocal calls
        calls += 1
        return {"type": "http.request", "body": b"x" * (1024 * 1024), "more_body": True}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/fixture",
            "headers": [(b"content-type", b"multipart/form-data; boundary=x")],
        },
        receive,
    )
    with pytest.raises(HTTPException) as error:
        await _bounded_form(request, upload=True)
    assert error.value.status_code == 413
    assert calls == MAX_FORM_BYTES // (1024 * 1024) + 1


@pytest.mark.anyio
async def test_small_form_still_decodes_and_large_fields_fail_closed():
    async def receive():
        return {"type": "http.request", "body": b"caption=Hello+world", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/fixture",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        },
        receive,
    )
    form = await _bounded_form(request)
    assert form["caption"] == "Hello world"
    await form.close()
