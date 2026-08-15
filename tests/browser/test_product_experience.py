from __future__ import annotations

from tests.browser.test_identity_flow import client_for, complete_setup


def test_today_reports_search_and_read_only_pwa_shell_are_browser_visible(tmp_path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        home = client.get("/home")
        assert "Today" in home.text
        assert 'href="/reports"' in home.text
        assert 'rel="manifest"' in home.text
        assert "unsafe-inline" not in home.headers["content-security-policy"]
        assert client.get("/reports").status_code == 200
        assert client.get("/search").status_code == 200
        worker = client.get("/static/service-worker.js")
        assert worker.status_code == 200
        assert 'method !== "GET"' in worker.text
        assert "indexedDB" not in worker.text
