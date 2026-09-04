from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from snaketracker.application.reports import KeeperReport, ReportRow, ReportService


class Animals:
    def list_profiles(self, _household_id):
        return (
            SimpleNamespace(
                animal_id=uuid4(),
                name="Nyx",
                type_label="Snake",
                species="Python regius",
                status="active",
            ),
        )

    def effective_history(self, _household_id, _animal_id):
        return ()


class Expenses:
    def list_expenses(self, _household_id):
        return ()


def test_collection_report_and_csv_are_stable_and_formula_safe() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)

    class FourGroupAnimals(Animals):
        def list_profiles(self, _household_id):
            return tuple(
                SimpleNamespace(
                    animal_id=uuid4(),
                    name=name,
                    type_label=label,
                    species=species,
                    status="active",
                )
                for name, label, species in (
                    ("Nyx", "Snake", "Python regius"),
                    ("Webster", "Spider", "Fictional burrowing spider"),
                    ("Sol", "Lizard", "Fictional ridge lizard"),
                    ("Onyx", "Scorpion", "Fictional forest scorpion"),
                )
            )

    service = ReportService(FourGroupAnimals(), Expenses())  # type: ignore[arg-type]
    report = service.collection(uuid4(), generated_at=now)

    assert report.columns == ("Name", "Type", "Species", "Status")
    assert {row.values[1] for row in report.rows} == {"Snake", "Spider", "Lizard", "Scorpion"}
    dangerous = KeeperReport("Export", ("Value",), (ReportRow(("=2+2",)),), now)
    assert service.csv(dangerous) == "Value\r\n'=2+2\r\n"


def test_care_report_excludes_registration_and_preserves_effective_notes() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)

    class CareAnimals(Animals):
        def effective_history(self, _household_id, _animal_id):
            return (
                SimpleNamespace(
                    event_type="animal.registered",
                    occurred_at=now,
                    title="Registered",
                    notes=None,
                ),
                SimpleNamespace(
                    event_type="animal.feeding_recorded",
                    occurred_at=now,
                    title="Accepted one mouse",
                    notes="Keeper observed a strong response",
                ),
                SimpleNamespace(
                    event_type="animal.cleaning_recorded",
                    occurred_at=now,
                    title="Spot cleaned",
                    notes=None,
                ),
            )

    report = ReportService(CareAnimals(), Expenses()).care(uuid4(), generated_at=now)  # type: ignore[arg-type]

    assert [row.values[2] for row in report.rows] == ["Accepted one mouse", "Spot cleaned"]
    assert report.rows[0].values[3] == "Keeper observed a strong response"
    assert report.rows[1].values[3] == ""


def test_expense_report_formats_minor_units_without_changing_authoritative_status() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)

    class RecordedExpenses(Expenses):
        def list_expenses(self, _household_id):
            return (
                SimpleNamespace(
                    occurred_at=now,
                    category="supplies",
                    amount_minor=1299,
                    currency="USD",
                    status="effective",
                ),
            )

    report = ReportService(Animals(), RecordedExpenses()).expenses(uuid4(), generated_at=now)  # type: ignore[arg-type]

    assert report.rows[0].values == (
        "2026-08-15T00:00+00:00",
        "supplies",
        "12.99",
        "USD",
        "effective",
    )
