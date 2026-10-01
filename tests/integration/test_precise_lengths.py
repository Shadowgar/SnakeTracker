from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from snaketracker.application import animals as commands
from snaketracker.application.analytics import AnimalAnalyticsService
from snaketracker.application.length_measurements import parse_length_input
from snaketracker.application.reports import ReportService
from snaketracker.platform.events.store import StreamKey
from snaketracker.presentation.animal_care_views import present_effective_care_events
from tests.integration.test_multispecies_animals import _register, _services
from tests.integration.test_reminders import _rule_command, _setup

NOW = datetime(2026, 8, 17, 16, tzinfo=UTC)
MEASURED = datetime(2026, 8, 16, 16, tzinfo=UTC)


def record_v2(animals, bootstrap, animal_id, value="48.50", unit="in", key="length-v2"):
    return animals.record_length(
        commands.RecordLengthV2Command(
            household_id=bootstrap.household_id,
            actor_user_id=bootstrap.user_id,
            animal_id=animal_id,
            correlation_id=uuid4(),
            idempotency_key=key,
            occurred_at=MEASURED,
            notes=None,
            **asdict(parse_length_input(value, unit)),
        )
    ).event


def correct_v2(animals, bootstrap, animal_id, target, value, unit, key):
    return animals.correct_length(
        commands.CorrectLengthV2Command(
            household_id=bootstrap.household_id,
            actor_user_id=bootstrap.user_id,
            actor_role="owner",
            animal_id=animal_id,
            target_event_id=target,
            idempotency_key=key,
            occurred_at=MEASURED,
            notes="Unit/value confirmed.",
            **asdict(parse_length_input(value, unit)),
        )
    ).event


def control(animals, bootstrap, animal_id, target, reinstate=False):
    cls = commands.ReinstateAnimalEventCommand if reinstate else commands.VoidAnimalEventCommand
    method = animals.reinstate_event if reinstate else animals.void_event
    return method(
        cls(
            bootstrap.household_id,
            bootstrap.user_id,
            "owner",
            animal_id,
            target,
            f"{'restore' if reinstate else 'void'}-{target}",
            "Confirmed.",
        )
    )


def test_mixed_lengths_corrections_consumers_void_reinstate_and_reload(tmp_path):
    animals, store, bootstrap, engine = _services(tmp_path)
    try:
        animal_id = _register(animals, bootstrap, "snake", "Precise").animal_id
        v1 = animals.record_length(
            commands.RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "length-v1",
                datetime(2026, 8, 1, tzinfo=UTC),
                900,
                None,
            )
        ).event
        v2 = record_v2(animals, bootstrap, animal_id)
        corrected_v1 = correct_v2(animals, bootstrap, animal_id, v1.event_id, "12.25", "cm", "cv1")
        corrected_v2 = correct_v2(animals, bootstrap, animal_id, v2.event_id, "48.50", "cm", "cv2")
        chain = correct_v2(
            animals, bootstrap, animal_id, corrected_v2.event_id, "49.50", "cm", "chain"
        )
        assert v1.schema_version == 1 and v1.payload.length_mm == 900
        assert chain.payload.length_um == 495000
        assert corrected_v2.payload.length_um == 485000
        points = (
            AnimalAnalyticsService(animals)
            .for_animal(bootstrap.household_id, animal_id, as_of=NOW.date())
            .measurements
        )
        assert {p.value for p in points} == {Decimal("122.5"), Decimal("495")}
        assert all(p.unit == "mm" for p in points)
        assert {p.display_value for p in points} == {"12.25", "49.50"}
        views = present_effective_care_events(
            animals.effective_history(bootstrap.household_id, animal_id)
        )
        assert {"12.25 cm", "49.50 cm"} <= {v.description for v in views}
        report = ReportService(animals, None).measurements(
            bootstrap.household_id, animal_id=animal_id, generated_at=NOW
        )
        assert len(report.rows) == 2
        assert {"122500", "495000"} == {r.values[6] for r in report.rows}
        assert str(v1.event_id) in ReportService.csv(report)
        assert str(chain.event_id) in ReportService.csv(report)
        control(animals, bootstrap, animal_id, v2.event_id)
        assert (
            len(
                ReportService(animals, None)
                .measurements(bootstrap.household_id, animal_id=animal_id, generated_at=NOW)
                .rows
            )
            == 1
        )
        control(animals, bootstrap, animal_id, v2.event_id, True)
        assert (
            len(
                ReportService(animals, None)
                .measurements(bootstrap.household_id, animal_id=animal_id, generated_at=NOW)
                .rows
            )
            == 2
        )
        reloaded = store.load_stream(StreamKey(bootstrap.household_id, "animal", animal_id))
        assert next(e for e in reloaded if e.event_id == v1.event_id).payload.length_mm == 900
        assert next(e for e in reloaded if e.event_id == chain.event_id).payload.length_um == 495000
        assert corrected_v1.schema_version == 2
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("field", "bad"),
    [("length_um", 1231901), ("entered_scale", True), ("entered_value_scaled", 4850.0)],
)
def test_precise_length_command_rejects_tuple_disagreement_before_writing(tmp_path, field, bad):
    animals, store, bootstrap, engine = _services(tmp_path)
    try:
        animal_id = _register(animals, bootstrap, "snake", "Reject").animal_id
        cmd = commands.RecordLengthV2Command(
            bootstrap.household_id,
            bootstrap.user_id,
            animal_id,
            uuid4(),
            "invalid",
            MEASURED,
            1231900,
            4850,
            2,
            "in",
            None,
        )
        with pytest.raises(commands.AnimalValidationError):
            animals.record_length(replace(cmd, **{field: bad}))
        assert len(store.load_stream(StreamKey(bootstrap.household_id, "animal", animal_id))) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("initial_version", (1, 2))
def test_length_reminder_sources_due_and_one_time_override_follow_mixed_history(
    tmp_path, initial_version
):
    engine, bootstrap, animals, _, animal_id, _, rules, facts, _ = _setup(tmp_path)
    try:
        rule = rules.create(
            _rule_command(
                bootstrap,
                animal_id,
                reminder_type="length",
                interval_days=5,
                override_due_at="2026-08-11T16:00:00+00:00",
            )
        )

        def fact():
            return next(
                item
                for item in facts.agenda_for(bootstrap.household_id, now=NOW)
                if item.rule_id == rule.rule_id
            )

        assert fact().explanation == "Owner due-date override"
        if initial_version == 1:
            v1 = animals.record_length(
                commands.RecordLengthCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    animal_id,
                    uuid4(),
                    "legacy",
                    MEASURED,
                    1232,
                    None,
                )
            ).event
        else:
            v1 = record_v2(animals, bootstrap, animal_id, key="precise-source")
        assert fact().source_event_id == v1.event_id
        assert fact().due_at == datetime(2026, 8, 21, 16, tzinfo=UTC)
        c1 = correct_v2(animals, bootstrap, animal_id, v1.event_id, "48.5", "in", "correct-legacy")
        assert fact().source_event_id == c1.event_id
        assert fact().due_at == datetime(2026, 8, 21, 16, tzinfo=UTC)
        c2 = correct_v2(animals, bootstrap, animal_id, c1.event_id, "48.5", "cm", "change-unit")
        assert fact().source_event_id == c2.event_id
        assert fact().due_at == datetime(2026, 8, 21, 16, tzinfo=UTC)
        control(animals, bootstrap, animal_id, v1.event_id)
        assert fact().source_event_id is None
        assert fact().due_at == datetime(2026, 8, 11, 16, tzinfo=UTC)
        assert fact().explanation == "Owner due-date override"
        control(animals, bootstrap, animal_id, v1.event_id, True)
        assert fact().source_event_id == c2.event_id
        assert fact().due_at == datetime(2026, 8, 21, 16, tzinfo=UTC)
    finally:
        engine.dispose()


def test_length_projection_rebuild_search_effective_values_and_catch_up(tmp_path):
    from snaketracker.infrastructure.product_experience.projections import (
        ensure_product_projection_generations,
        product_projection_registry,
    )
    from snaketracker.infrastructure.product_experience.read_models import (
        SQLAlchemyProjectedEventReader,
    )
    from snaketracker.infrastructure.search.fts import SQLAlchemyFTSSearchRepository
    from snaketracker.worker.projections import ProjectionWorker

    animals, _store, bootstrap, engine = _services(tmp_path)
    try:
        animal_id = _register(animals, bootstrap, "snake", "Replay").animal_id
        manager = ensure_product_projection_generations(engine)
        worker = ProjectionWorker(engine, manager, product_projection_registry)
        search = SQLAlchemyFTSSearchRepository(engine, manager)
        v2 = record_v2(animals, bootstrap, animal_id)
        worker.run_once()
        assert search.search(bootstrap.household_id, frozenset(), "48.50", limit=50)
        c1 = correct_v2(animals, bootstrap, animal_id, v2.event_id, "48.50", "cm", "search-c1")
        chain = correct_v2(animals, bootstrap, animal_id, c1.event_id, "49.50", "cm", "search-c2")
        worker.run_once()
        assert not search.search(bootstrap.household_id, frozenset(), "48.50", limit=50)
        assert len(search.search(bootstrap.household_id, frozenset(), "49.50", limit=50)) == 1
        control(animals, bootstrap, animal_id, chain.event_id)
        worker.run_once()
        assert len(search.search(bootstrap.household_id, frozenset(), "48.50", limit=50)) == 1
        assert not search.search(bootstrap.household_id, frozenset(), "49.50", limit=50)
        control(animals, bootstrap, animal_id, chain.event_id, True)
        control(animals, bootstrap, animal_id, v2.event_id)
        worker.run_once()
        assert not search.search(bootstrap.household_id, frozenset(), "49.50", limit=50)
        control(animals, bootstrap, animal_id, v2.event_id, True)
        worker.run_once()
        assert len(search.search(bootstrap.household_id, frozenset(), "49.50", limit=50)) == 1
        reader = SQLAlchemyProjectedEventReader(
            engine, manager, product_projection_registry, "measurement_analytics"
        )
        before = AnimalAnalyticsService(animals, projected_events=reader).for_animal(
            bootstrap.household_id, animal_id, as_of=NOW.date()
        )
        rebuilt = manager.rebuild("insights")
        assert rebuilt is not None
        after = AnimalAnalyticsService(animals, projected_events=reader).for_animal(
            bootstrap.household_id, animal_id, as_of=NOW.date()
        )
        assert before.measurements == after.measurements
        report_reader = SQLAlchemyProjectedEventReader(
            engine, manager, product_projection_registry, "report_facts"
        )
        async_report = ReportService(animals, None, projected_events=report_reader).measurements(
            bootstrap.household_id, animal_id=animal_id, generated_at=NOW
        )
        direct_report = ReportService(animals, None).measurements(
            bootstrap.household_id, animal_id=animal_id, generated_at=NOW
        )
        assert async_report == direct_report
        manager.rebuild("search")
        assert len(search.search(bootstrap.household_id, frozenset(), "49.50", limit=50)) == 1
        assert manager.freshness("search", now=NOW).lag_events == 0
        assert manager.freshness("insights", now=NOW).lag_events == 0
        assert next(p for p in after.measurements if p.kind == "length").value == Decimal("495")
    finally:
        engine.dispose()


def test_precise_length_idempotency_retains_tuple_precision_and_rejects_changed_commands(tmp_path):
    from snaketracker.platform.events.store import IdempotencyConflictError

    animals, store, bootstrap, engine = _services(tmp_path)
    try:
        animal_id = _register(animals, bootstrap, "snake", "Idempotent").animal_id
        first = record_v2(animals, bootstrap, animal_id)
        repeated = record_v2(animals, bootstrap, animal_id)
        assert repeated.event_id == first.event_id
        assert repeated.payload.entered_scale == 2
        with pytest.raises(IdempotencyConflictError):
            record_v2(animals, bootstrap, animal_id, value="48.5")
        corrected = correct_v2(animals, bootstrap, animal_id, first.event_id, "48.50", "cm", "fix")
        retry = correct_v2(animals, bootstrap, animal_id, first.event_id, "48.50", "cm", "fix")
        assert retry.event_id == corrected.event_id
        with pytest.raises(IdempotencyConflictError):
            correct_v2(animals, bootstrap, animal_id, first.event_id, "48.50", "in", "fix")
        invalid = commands.CorrectLengthV2Command(
            bootstrap.household_id,
            bootstrap.user_id,
            "owner",
            animal_id,
            first.event_id,
            "bad-correction",
            MEASURED,
            485000,
            4850,
            2.0,
            "cm",
            None,
        )
        with pytest.raises(commands.AnimalValidationError):
            animals.correct_length(invalid)
        assert len(store.load_stream(StreamKey(bootstrap.household_id, "animal", animal_id))) == 3
    finally:
        engine.dispose()


def test_precise_correction_can_extend_a_historical_v1_correction_chain(tmp_path):
    animals, store, bootstrap, engine = _services(tmp_path)
    try:
        animal_id = _register(animals, bootstrap, "snake", "Historical chain").animal_id
        legacy = animals.record_length(
            commands.RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "legacy-root",
                MEASURED,
                900,
                None,
            )
        ).event
        correction = animals.correct_length(
            commands.CorrectLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal_id,
                legacy.event_id,
                "legacy-correction",
                MEASURED,
                950,
                None,
            )
        ).event
        precise = correct_v2(
            animals, bootstrap, animal_id, correction.event_id, "48.5", "in", "precise-legacy-chain"
        )
        assert precise.payload.target_event_id == correction.event_id
        assert precise.payload.length_um == 1231900
        assert precise.causation_id == correction.event_id
        assert precise.correlation_id == legacy.correlation_id
        points = (
            AnimalAnalyticsService(animals)
            .for_animal(bootstrap.household_id, animal_id, as_of=NOW.date())
            .measurements
        )
        assert [(p.value, p.display_value, p.display_unit) for p in points] == [
            (Decimal("1231.9"), "48.5", "in")
        ]
        report = ReportService(animals, None).measurements(
            bootstrap.household_id, animal_id=animal_id, generated_at=NOW
        )
        assert report.rows[0].values[1:3] == (str(precise.event_id), str(legacy.event_id))
        control(animals, bootstrap, animal_id, precise.event_id)
        effective = animals.effective_history(bootstrap.household_id, animal_id)
        assert next(e for e in effective if e.event_type == "animal.length_corrected") == correction
        control(animals, bootstrap, animal_id, precise.event_id, True)
        assert precise in animals.effective_history(bootstrap.household_id, animal_id)
        replayed = store.load_stream(StreamKey(bootstrap.household_id, "animal", animal_id))
        assert next(e for e in replayed if e.event_id == legacy.event_id).payload.length_mm == 900
        assert (
            next(e for e in replayed if e.event_id == correction.event_id).payload.length_mm == 950
        )
    finally:
        engine.dispose()


def test_length_search_provenance_keeps_prior_root_position_and_tracks_reinstatement(tmp_path):
    from sqlalchemy import text

    from snaketracker.infrastructure.product_experience.projections import (
        ensure_product_projection_generations,
        product_projection_registry,
    )
    from snaketracker.worker.projections import ProjectionWorker

    animals, _store, bootstrap, engine = _services(tmp_path)
    try:
        animal_id = _register(animals, bootstrap, "snake", "Stable provenance").animal_id
        first = animals.record_length(
            commands.RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "prior-v1-position",
                MEASURED,
                900,
                None,
            )
        ).event
        manager = ensure_product_projection_generations(engine)
        worker = ProjectionWorker(engine, manager, product_projection_registry)

        def position(event_id):
            table = manager.active_layout("search").component("global_search_fts", "content")
            with engine.connect() as connection:
                return connection.execute(
                    text(f'SELECT source_global_position FROM "{table}" WHERE document_key=:key'),
                    {"key": f"event:{event_id}"},
                ).scalar_one()

        def global_position(event_id):
            with engine.connect() as connection:
                return connection.execute(
                    text("SELECT global_position FROM domain_events WHERE event_id=:event"),
                    {"event": str(event_id)},
                ).scalar_one()

        first_position = position(first.event_id)
        assert first_position == global_position(first.event_id)
        second = record_v2(animals, bootstrap, animal_id, key="unrelated-second-length")
        worker.run_once()
        assert position(first.event_id) == first_position
        assert position(second.event_id) == global_position(second.event_id)
        corrected = correct_v2(
            animals, bootstrap, animal_id, second.event_id, "48.5", "cm", "provenance-correct"
        )
        worker.run_once()
        assert position(first.event_id) == first_position
        assert position(second.event_id) == global_position(corrected.event_id)
        control(animals, bootstrap, animal_id, second.event_id)
        restored = control(animals, bootstrap, animal_id, second.event_id, True)
        worker.run_once()
        assert position(first.event_id) == first_position
        assert position(second.event_id) == global_position(restored.event.event_id)
        manager.rebuild("search")
        assert position(first.event_id) == first_position
        assert position(second.event_id) == global_position(restored.event.event_id)
    finally:
        engine.dispose()
