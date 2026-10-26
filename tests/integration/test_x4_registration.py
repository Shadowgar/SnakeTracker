"""Disposable registration persistence, retry, and replay qualification for X4."""

from dataclasses import replace
from uuid import uuid4

import pytest

from snaketracker.application.animals import AnimalValidationError, RegisterAnimalCommand
from snaketracker.domains.animals import capabilities
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.platform.events.store import IdempotencyConflictError
from tests.integration.test_multispecies_animals import _services


def frog_command(bootstrap):
    return RegisterAnimalCommand(
        household_id=bootstrap.household_id,
        actor_user_id=bootstrap.user_id,
        correlation_id=uuid4(),
        idempotency_key="x4-register-fern",
        name="Fern",
        species="Keeper entered frog",
        morph=None,
        genetics=None,
        sex=None,
        birth_hatch_date=None,
        acquisition_date=None,
        breeder_source=None,
        notes="Observed frog",
        animal_type="amphibian",
    )


def immutable_rows(engine):
    with engine.connect() as connection:
        return {
            table: connection.exec_driver_sql(f"SELECT * FROM {table}").all()
            for table in ("domain_events", "event_streams", "idempotency_operations")
        }


def test_frog_registration_writes_v3_and_rebuilds_same_profile_without_rewriting_events(tmp_path):
    service, store, bootstrap, engine = _services(tmp_path)
    try:
        registered = service.register(frog_command(bootstrap))
        assert registered.profile.capability_profile_identity == "amphibian.v1"
        events = store.load_stream(registered.stream_key)
        assert len(events) == 1
        assert events[0].schema_version == 3
        assert type(events[0].payload).__name__ == "AnimalRegisteredV3"
        assert events[0].payload.capability_profile == "amphibian.v1"
        before = immutable_rows(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("DELETE FROM animal_current")
            SQLAlchemyAnimalCurrentProjection(engine).apply(connection, events)
        assert (
            service.profile_for(bootstrap.household_id, registered.animal_id) == registered.profile
        )
        assert immutable_rows(engine) == before
    finally:
        engine.dispose()


@pytest.mark.parametrize("policy", ["successor", "disabled"])
def test_completed_frog_retry_preserves_original_result_hash_and_events(
    tmp_path, monkeypatch, policy
):
    from snaketracker.application import animals
    from snaketracker.platform.events import registry as contracts

    service, store, bootstrap, engine = _services(tmp_path)
    try:
        command = frog_command(bootstrap)
        original = service.register(command)
        before = immutable_rows(engine)
        profile = capabilities.animal_capability_registry.require("amphibian.v1")
        retired = replace(profile, registration_eligible=False, registration_default=False)
        group = capabilities.animal_capability_registry.group("amphibian")
        profiles = (retired, replace(profile, version=2)) if policy == "successor" else (retired,)
        registry = capabilities.AnimalCapabilityRegistry(
            profiles, groups=(group if policy == "successor" else replace(group, enabled=False),)
        )
        for module in (animals, capabilities, contracts):
            monkeypatch.setattr(module, "animal_capability_registry", registry)
        retry = service.register(replace(command, correlation_id=uuid4()))
        assert retry == original
        assert len(store.load_stream(original.stream_key)) == 1
        assert immutable_rows(engine) == before
        for changed in (replace(command, name="Different"), replace(command, animal_type="snake")):
            with pytest.raises(IdempotencyConflictError):
                service.register(changed)
        assert immutable_rows(engine) == before
        new_command = replace(command, name="New", idempotency_key="new-frog")
        if policy == "successor":
            new = service.register(new_command)
            assert new.profile.capability_profile_identity == "amphibian.v2"
            assert store.load_stream(new.stream_key)[0].payload.capability_profile == "amphibian.v2"
        else:
            with pytest.raises(AnimalValidationError, match="registration"):
                service.register(new_command)
            assert immutable_rows(engine) == before
    finally:
        engine.dispose()
