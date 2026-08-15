from __future__ import annotations

from uuid import uuid4

from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from


def test_today_reports_search_and_read_only_pwa_shell_are_browser_visible(tmp_path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        home = client.get("/home")
        assert "Today" in home.text
        assert 'href="/reports"' in home.text
        assert 'rel="manifest"' in home.text
        assert "unsafe-inline" not in home.headers["content-security-policy"]
        assert client.get("/reports").status_code == 200
        assert client.get("/reports/collection").status_code == 200
        assert client.get("/reports/collection.csv").headers["content-type"].startswith("text/csv")
        assert client.get("/reports/care").status_code == 200
        assert client.get("/reports/care.csv").status_code == 200
        assert client.get("/reports/expenses").status_code == 200
        assert client.get("/reports/expenses.csv").status_code == 200
        assert client.get("/search").status_code == 200
        assert client.get(f"/animals/{uuid4()}/analytics").status_code == 404
        assert client.get(f"/api/v1/animals/{uuid4()}/analytics/measurements").status_code == 404

        form = client.get("/animals/new")
        registered = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "Analytics fixture",
            },
            follow_redirects=False,
        )
        animal_url = registered.headers["location"]
        analytics = client.get(f"{animal_url}/analytics")
        assert analytics.status_code == 200
        assert "Nyx trends" in analytics.text
        data = client.get(f"/api/v1{animal_url}/analytics/measurements")
        assert data.status_code == 200
        assert data.json()["schema_version"] == 1
        assert (
            client.get(
                f"/api/v1{animal_url}/analytics/measurements",
                headers={"If-None-Match": data.headers["etag"]},
            ).status_code
            == 304
        )
        worker = client.get("/static/service-worker.js")
        assert worker.status_code == 200
        assert 'method !== "GET"' in worker.text
        assert "indexedDB" not in worker.text
