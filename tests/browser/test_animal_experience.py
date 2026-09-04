from __future__ import annotations

from pathlib import Path

from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from


def _register(client, *, name: str, animal_type: str, species: str) -> str:
    form = client.get("/animals/new")
    response = client.post(
        "/animals",
        data={
            "csrf_token": csrf_from(form.text),
            "idempotency_key": f"pass3-{animal_type}",
            "animal_type": animal_type,
            "name": name,
            "species": species,
            "sex": "",
            "morph": "",
            "genetics": "",
            "birth_hatch_date": "",
            "acquisition_date": "",
            "breeder_source": "",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"]


def test_animal_experience_has_distinct_profile_sections_and_focused_editors(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        animal_url = _register(client, name="Nyx", animal_type="snake", species="Python regius")

        sections = {
            "": ("Overview", 'aria-current="page">Overview'),
            "/timeline": ("History", 'aria-current="page">History'),
            "/analytics": ("Trends", 'aria-current="page">Trends'),
            "/care": ("Care schedules", 'aria-current="page">Care'),
        }
        for suffix, (copy, active_link) in sections.items():
            page = client.get(f"{animal_url}{suffix}")
            assert page.status_code == 200
            assert copy in page.text
            assert active_link in page.text
            assert "Next care" in page.text

        care = client.get(f"{animal_url}/care")
        assert "Not scheduled" in care.text
        assert "Set schedule" in care.text
        assert f"{animal_url}/care-schedule/feeding/edit" in care.text

        schedule = client.get(f"{animal_url}/care-schedule/feeding/edit")
        assert schedule.status_code == 200
        assert schedule.text.count("schedule-form") == 0
        assert "Override next due date" in schedule.text
        assert "Optional one-time adjustment" in schedule.text
        feeding = client.post(
            f"{animal_url}/feedings",
            data={
                "csrf_token": csrf_from(schedule.text),
                "idempotency_key": "pass3-feeding",
                "occurred_at": "2026-08-27T08:00",
                "prey_type": "mouse",
                "prey_size": "small",
                "preparation_method": "frozen_thawed",
                "quantity": "1",
                "outcome": "accepted",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert feeding.status_code == 303
        saved = client.post(
            f"{animal_url}/care-schedule/feeding",
            data={
                "csrf_token": csrf_from(schedule.text),
                "idempotency_key": "pass3-feeding-schedule",
                "expected_stream_version": "0",
                "return_to": "care",
                "enabled": "true",
                "interval_days": "7",
                "override_due_at": "",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert saved.headers["location"] == f"{animal_url}/care"
        assert client.get("/home").status_code == 200
        scheduled_profile = client.get(animal_url)
        assert scheduled_profile.status_code == 200
        assert "Every 7 days after last accepted feeding" in scheduled_profile.text

        for kind, expected in (
            ("photo", "Profile photo"),
            ("enclosure", "Move enclosure"),
            ("status", "Update status"),
        ):
            focused = client.get(f"{animal_url}/{kind}")
            assert focused.status_code == 200
            assert expected in focused.text
            assert focused.text.count('<form class="card form-stack"') == 1

        feeding = client.get(f"{animal_url}/feedings/new?return_to=care")
        assert feeding.status_code == 200
        assert "Quick care" in feeding.text
        assert 'name="return_to" value="care"' in feeding.text


def test_animal_experience_actions_and_trends_follow_capability_registry(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        snake_url = _register(client, name="Snake", animal_type="snake", species="Python regius")
        spider_url = _register(
            client, name="Spider", animal_type="spider", species="Grammostola pulchra"
        )

        snake = client.get(snake_url).text
        spider = client.get(spider_url).text
        assert "Record shed" in snake
        assert "Record molt" not in snake
        assert "Record molt" in spider
        assert "Premolt observation" in spider
        assert "Record shed" not in spider

        spider_trends = client.get(f"{spider_url}/analytics").text
        assert "Molt estimate unavailable" in spider_trends
        assert "Shed estimate unavailable" not in spider_trends
        assert "Not enough history yet" in spider_trends
