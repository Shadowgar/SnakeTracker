from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from snaketracker.application.purchases import (
    CurrencyValue,
    InventoryCostActivity,
    InventoryCostActivityPoint,
    InventoryCostSummary,
    PurchaseCurrent,
    PurchaseLineCurrent,
)
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
        "Other expense",
        "supplies",
        "12.99",
        "USD",
        "effective",
    )


def test_inventory_report_separates_cash_consumption_value_and_currency() -> None:
    household_id = uuid4()
    item_id = uuid4()
    now = datetime(2026, 9, 13, 16, tzinfo=UTC)
    item = SimpleNamespace(
        household_id=household_id,
        item_id=item_id,
        name="Medium mice",
        inventory_type="food",
        type_label="Food",
        stock_role="care_supply",
        stock_role_label="Care supply",
        status="active",
        needs_setup=False,
        recount_interval_days=30,
        reorder_threshold_scaled=10_000,
        target_quantity_scaled=40_000,
        on_hand_quantity_scaled=32_000,
        available_quantity_scaled=32_000,
        unit_label="Each",
        unit_symbol="each",
    )
    usd_line = PurchaseLineCurrent(
        uuid4(), item_id, item.name, 50_000, "each", 6_500, 6_500, uuid4(), "active"
    )
    eur_line = PurchaseLineCurrent(
        uuid4(), item_id, item.name, 1_000, "each", 100, 100, uuid4(), "active"
    )
    purchases = (
        PurchaseCurrent(
            household_id,
            uuid4(),
            "Known supplier",
            "USD",
            None,
            None,
            datetime(2026, 9, 1, tzinfo=UTC),
            6_500,
            0,
            0,
            0,
            6_500,
            "active",
            1,
            uuid4(),
            (usd_line,),
        ),
        PurchaseCurrent(
            household_id,
            uuid4(),
            "Euro supplier",
            "EUR",
            None,
            None,
            datetime(2026, 9, 2, tzinfo=UTC),
            100,
            0,
            0,
            0,
            100,
            "active",
            1,
            uuid4(),
            (eur_line,),
        ),
    )
    activity_ends: list[datetime] = []

    class Inventory:
        def list_balances(self, _household_id, *, status):
            assert status == "active"
            return (item,)

        def balance_for(self, requested_household, requested_item):
            return (
                item if (requested_household, requested_item) == (household_id, item_id) else None
            )

    class Purchases:
        def list_purchases(self, _household_id):
            return purchases

        def cost_summary_for(self, _household_id, _item_id):
            return InventoryCostSummary(
                household_id,
                item_id,
                (CurrencyValue("EUR", 100), CurrencyValue("USD", 4_160)),
                (CurrencyValue("USD", 2_340),),
                0,
            )

        def cost_activity_for(self, _household_id, _item_id, _start, _end):
            activity_ends.append(_end)
            return InventoryCostActivity(
                household_id,
                item_id,
                (CurrencyValue("USD", 2_340),),
                (),
                (),
            )

        def cost_activity_points_for(self, _household_id, _item_id, _start, _end):
            return (
                InventoryCostActivityPoint(
                    household_id,
                    item_id,
                    datetime(2026, 9, 5, tzinfo=UTC),
                    "consumption",
                    "USD",
                    2_340,
                ),
            )

    class Intelligence:
        def insight_for(self, _household_id, _item_id, _timezone, _as_of):
            return SimpleNamespace(
                used_30_scaled=6_000,
                used_90_scaled=18_000,
                daily_rate_scaled=Decimal(200),
                available=True,
                lag_events=0,
                reorder_state="stable",
                verification_state="due",
                usage_state="supported",
            )

    class OtherExpenses(Expenses):
        def list_expenses(self, _household_id):
            return (
                SimpleNamespace(
                    occurred_at=datetime(2026, 9, 3, tzinfo=UTC),
                    amount_minor=1_200,
                    currency="USD",
                    category="vet_care",
                    status="active",
                ),
            )

    service = ReportService(
        Animals(),
        OtherExpenses(),
        inventory=Inventory(),  # type: ignore[arg-type]
        purchases=Purchases(),  # type: ignore[arg-type]
        inventory_intelligence=Intelligence(),  # type: ignore[arg-type]
    )
    report = service.inventory_collection(
        household_id,
        household_timezone="UTC",
        generated_at=now,
        period_days=90,
        currency="USD",
    )

    assert report.currencies == ("EUR", "USD")
    assert report.supply_purchase_cash_minor == 6_500
    assert report.other_expense_cash_minor == 1_200
    assert report.consumption_value_minor == 2_340
    assert report.current_known_value_minor == 4_160
    assert report.items[0].known_value_reconciles is True
    assert report.spending_trend_supported is True
    assert report.spending_trend_direction == "increased"
    assert sum(bucket.known_consumption_value_minor for bucket in report.period_buckets) == 2_340
    assert report.spending_categories[-1].label == "Other expenses · Vet Care"
    assert activity_ends[-1] == now
    assert report.items[0].estimate is not None
    assert report.items[0].estimate.quantity_scaled == 26_000
    assert report.items[0].estimate.amount_minor == 3_380
    assert report.check_due_items == 1
    assert "6500.00" not in service.csv(service.inventory_collection_csv(report))


def test_inventory_report_rejects_currency_mixing() -> None:
    from snaketracker.application.reports import _selected_currency

    assert _selected_currency("USD", ("EUR", "USD")) == "USD"
    try:
        _selected_currency("GBP", ("EUR", "USD"))
    except ValueError as error:
        assert "represented" in str(error)
    else:
        raise AssertionError("An absent currency must not be silently mixed or substituted.")


def test_inventory_report_rejects_unconfigured_dependencies_and_period() -> None:
    service = ReportService(Animals(), Expenses())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="not configured"):
        service.inventory_collection(
            uuid4(),
            household_timezone="UTC",
            generated_at=datetime(2026, 9, 13, tzinfo=UTC),
            period_days=30,
        )

    from snaketracker.application.reports import _report_period

    with pytest.raises(ValueError, match="30 or 90"):
        _report_period(datetime(2026, 9, 13, tzinfo=UTC), "UTC", 31)


def test_spending_estimate_requires_price_and_positive_replenishment() -> None:
    from snaketracker.application.reports import _spending_estimate

    item = SimpleNamespace(
        stock_role="care_supply",
        target_quantity_scaled=None,
        reorder_threshold_scaled=5_000,
        on_hand_quantity_scaled=10_000,
        available_quantity_scaled=10_000,
    )
    insight = SimpleNamespace(available=True, daily_rate_scaled=Decimal(100))
    as_of = datetime(2026, 9, 13, tzinfo=UTC)
    assert _spending_estimate(item, insight, (), 30, "USD", as_of) is None

    line = PurchaseLineCurrent(
        uuid4(), uuid4(), "Supply", 10_000, "each", 1_000, 1_000, uuid4(), "active"
    )
    purchase = PurchaseCurrent(
        uuid4(),
        uuid4(),
        "Supplier",
        "USD",
        None,
        None,
        datetime(2026, 9, 1, tzinfo=UTC),
        1_000,
        0,
        0,
        0,
        1_000,
        "active",
        1,
        uuid4(),
        (line,),
    )
    assert _spending_estimate(item, insight, ((purchase, line),), 30, "USD", as_of) is None
    stale = replace(purchase, occurred_at=datetime(2025, 1, 1, tzinfo=UTC))
    assert _spending_estimate(item, insight, ((stale, line),), 30, "USD", as_of) is None
