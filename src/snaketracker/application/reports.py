"""Accessible HTML/CSV keeper reports derived from current and effective read models."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from snaketracker.application.animals import AnimalService
from snaketracker.application.expenses import ExpenseService
from snaketracker.application.projected_events import ProjectedEventReader
from snaketracker.platform.events.corrections import evaluate_effective_events
from snaketracker.platform.events.envelope import DomainEvent


@dataclass(frozen=True, slots=True)
class ReportRow:
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KeeperReport:
    title: str
    columns: tuple[str, ...]
    rows: tuple[ReportRow, ...]
    generated_at: datetime


class ReportService:
    def __init__(
        self,
        animals: AnimalService,
        expenses: ExpenseService,
        projected_events: ProjectedEventReader | None = None,
    ) -> None:
        self._animals = animals
        self._expenses = expenses
        self._projected_events = projected_events

    def collection(self, household_id: UUID, *, generated_at: datetime) -> KeeperReport:
        rows = tuple(
            ReportRow((item.name, item.type_label, item.species, item.status))
            for item in self._animals.list_profiles(household_id)
        )
        return KeeperReport(
            "Collection",
            ("Name", "Type", "Species", "Status"),
            rows,
            generated_at,
        )

    def care(self, household_id: UUID, *, generated_at: datetime) -> KeeperReport:
        rows: list[ReportRow] = []
        projected_by_animal: dict[UUID, list[DomainEvent]] | None = None
        if self._projected_events is not None:
            projected_by_animal = {}
            for event in evaluate_effective_events(
                self._projected_events.events_for(household_id, stream_type="animal")
            ):
                projected_by_animal.setdefault(event.stream_id, []).append(event)
        for animal in self._animals.list_profiles(household_id):
            history = (
                tuple(projected_by_animal.get(animal.animal_id, ()))
                if projected_by_animal is not None
                else self._animals.effective_history(household_id, animal.animal_id)
            )
            for event in history:
                if event.event_type == "animal.registered":
                    continue
                rows.append(
                    ReportRow(
                        (
                            animal.name,
                            event.occurred_at.isoformat(timespec="minutes"),
                            event.title,
                            event.notes or "",
                        )
                    )
                )
        return KeeperReport(
            "Effective care history",
            ("Animal", "Occurred", "Record", "Notes"),
            tuple(rows),
            generated_at,
        )

    def expenses(self, household_id: UUID, *, generated_at: datetime) -> KeeperReport:
        rows = tuple(
            ReportRow(
                (
                    item.occurred_at.isoformat(timespec="minutes"),
                    item.category,
                    f"{item.amount_minor / 100:.2f}",
                    item.currency,
                    item.status,
                )
            )
            for item in self._expenses.list_expenses(household_id)
        )
        return KeeperReport(
            "Expenses",
            ("Occurred", "Category", "Amount", "Currency", "Status"),
            rows,
            generated_at,
        )

    @staticmethod
    def csv(report: KeeperReport) -> str:
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(report.columns)
        for row in report.rows:
            writer.writerow(tuple(_csv_safe(value) for value in row.values))
        return stream.getvalue()


def _csv_safe(value: str) -> str:
    return f"'{value}" if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
