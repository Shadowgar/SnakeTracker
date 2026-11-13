"""Anonymous M9 delivery is gated, bounded and never stored by caches."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(*, enabled=False, per_client=240, total=1200):
    from snaketracker.presentation.sharing_guard import PublicSharingGuard

    app = FastAPI()
    app.add_middleware(PublicSharingGuard, enabled=enabled, per_client=per_client, total=total)

    @app.get("/p/{slug}")
    def public(slug: str):
        return {"title": "Deliberately published"}

    @app.get("/private")
    def private():
        return {"private": True}

    return TestClient(app)


def test_disabled_routes_are_indistinguishable_and_not_cached():
    with _client() as client:
        for path in ["/p/example", "/c/example", "/m/photo", "/p/nonexistent"]:
            response = client.get(path)
            assert response.status_code == 404
            assert response.text == "Not found"
            assert "no-store" in response.headers["cache-control"]
            assert response.headers["referrer-policy"] == "no-referrer"
            assert not response.headers.get("set-cookie")
        assert client.get("/private").status_code == 200


def test_enabled_head_missing_routes_and_rate_limits_fail_without_cache():
    with _client(enabled=True, per_client=2) as client:
        assert client.get("/p/example").status_code == 200
        assert client.head("/m/missing").status_code == 404
        denied = client.get("/p/example", headers={"x-forwarded-for": "198.51.100.41"})
        assert denied.status_code == 429
        assert denied.headers["retry-after"] == "60"
        assert "no-store" in denied.headers["cache-control"]


def test_limiter_has_a_global_budget_and_bounded_client_table():
    from snaketracker.presentation.sharing_guard import PublicRequestBudget

    budget = PublicRequestBudget(per_client=3, total=4, max_clients=2)
    assert budget.allow("a", now=0)
    assert budget.allow("b", now=0)
    assert not budget.allow("c", now=0)
    assert budget.allow("a", now=0)
    assert budget.allow("b", now=0)
    assert not budget.allow("b", now=0)
    assert budget.allow("c", now=61)


def test_public_failures_are_generic_and_never_cached():
    from snaketracker.presentation.sharing_guard import PublicSharingGuard

    app = FastAPI()
    app.add_middleware(PublicSharingGuard, enabled=True)

    @app.get("/p/broken")
    def broken():
        raise RuntimeError("private storage path must not be exposed")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/p/broken")
        assert response.status_code == 500
        assert "no-store" in response.headers["cache-control"]
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "private storage path" not in response.text
