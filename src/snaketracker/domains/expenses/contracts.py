"""Versioned event payloads owned by Expense streams."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExpenseRecordedV1:
    expense_id: UUID
    amount_minor: int
    currency: str
    category: str
    payee: str | None
    reference: str | None


@dataclass(frozen=True, slots=True)
class ExpenseCorrectedV1:
    target_event_id: UUID
    amount_minor: int
    currency: str
    category: str
    payee: str | None
    reference: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ExpenseVoidedV1:
    target_event_id: UUID
    reason: str
