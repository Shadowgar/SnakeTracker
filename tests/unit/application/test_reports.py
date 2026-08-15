from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from snaketracker.application.reports import KeeperReport, ReportRow, ReportService


class Animals:
    def list_profiles(self, _household_id):
        return (
            SimpleNamespace(
                name="Nyx", type_label="Snake", species="Python regius", status="active"
            ),
        )

    def effective_history(self, _household_id, _animal_id):
        return ()


class Expenses:
    def list_expenses(self, _household_id):
        return ()


def test_collection_report_and_csv_are_stable_and_formula_safe() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)
    service = ReportService(Animals(), Expenses())  # type: ignore[arg-type]
    report = service.collection(uuid4(), generated_at=now)

    assert report.columns == ("Name", "Type", "Species", "Status")
    assert report.rows[0].values == ("Nyx", "Snake", "Python regius", "active")
    dangerous = KeeperReport("Export", ("Value",), (ReportRow(("=2+2",)),), now)
    assert service.csv(dangerous) == "Value\r\n'=2+2\r\n"
