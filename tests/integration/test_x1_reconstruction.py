from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

from snaketracker.application.animals import RecordWeightCommand, UpdateAnimalProfileCommand
from snaketracker.application.reminders import CreateReminderRuleCommand, ReminderRuleService
from snaketracker.domains.animals import capabilities
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from tests.integration.test_multispecies_animals import NOW, _register, _services


@pytest.mark.parametrize("group", ["snake", "spider", "lizard", "scorpion"])
def test_historical_profile_remains_editable_actionable_and_reconstructible(
    tmp_path, monkeypatch, group
):
    from snaketracker.application import animals, reminders
    from snaketracker.platform.events import registry as event_registry

    service, store, bootstrap, engine = _services(tmp_path)
    try:
        original = _register(service, bootstrap, group, "Historical")
        readable = tuple(
            replace(
                capabilities.animal_capability_registry.require(identity),
                registration_eligible=False,
                registration_default=False,
            )
            for identity in capabilities.animal_capability_registry.identities
        )
        isolated = capabilities.AnimalCapabilityRegistry(
            readable,
            groups=tuple(
                replace(item, enabled=False)
                for item in capabilities.animal_capability_registry.groups
            ),
        )
        for module in (capabilities, animals, reminders, event_registry):
            if hasattr(module, "animal_capability_registry"):
                monkeypatch.setattr(module, "animal_capability_registry", isolated)
        service.update_profile(
            UpdateAnimalProfileCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                original.animal_id,
                uuid4(),
                "historical-edit",
                "Historical edited",
                original.profile.species,
                None,
                None,
                None,
                None,
                None,
                None,
                "Retired profile stays editable",
            )
        )
        service.record_weight(
            RecordWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                original.animal_id,
                uuid4(),
                "historical-weight",
                NOW,
                100,
                None,
            )
        )
        rule = ReminderRuleService(store, SQLAlchemyReminderProjection(engine)).create(
            CreateReminderRuleCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "historical-reminder",
                "animal",
                original.animal_id,
                "weight",
                "event_relative",
                30,
                None,
                None,
                True,
                "local",
            )
        )
        assert rule.current.reminder_type == "weight"
        current = service.profile_for(bootstrap.household_id, original.animal_id)
        assert current is not None
        assert current.capability_profile_identity == f"{group}.v1"
        assert (
            capabilities.AnimalAnalyticsKind.WEIGHT
            in isolated.require(f"{group}.v1").analytics_kinds
        )
        events = store.load_stream(original.stream_key)
        with engine.begin() as connection:
            expected = (
                connection.execute(text("SELECT * FROM animal_current ORDER BY animal_id"))
                .mappings()
                .all()
            )
            connection.exec_driver_sql(
                "CREATE TEMP TABLE animal_current AS SELECT * FROM main.animal_current WHERE 0"
            )
            SQLAlchemyAnimalCurrentProjection(engine).apply(connection, events)
            actual = (
                connection.execute(text("SELECT * FROM temp.animal_current ORDER BY animal_id"))
                .mappings()
                .all()
            )
            assert actual == expected
            connection.exec_driver_sql("DROP TABLE temp.animal_current")
        assert store.load_stream(original.stream_key) == events
    finally:
        engine.dispose()
