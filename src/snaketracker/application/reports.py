"""Accessible HTML/CSV keeper reports derived from current and effective read models."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from snaketracker.application.animals import AnimalService
from snaketracker.application.expenses import ExpenseCurrent, ExpenseService
from snaketracker.application.inventory import InventoryBalance, InventoryService
from snaketracker.application.inventory_intelligence import (
    InventoryInsight,
    InventoryIntelligenceProjection,
    stock_check_is_due,
)
from snaketracker.application.projected_events import ProjectedEventReader
from snaketracker.application.purchases import (
    CurrencyValue,
    InventoryCostActivity,
    InventoryCostActivityPoint,
    InventoryCostSummary,
    PurchaseCurrent,
    PurchaseLineCurrent,
    PurchaseService,
)
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


@dataclass(frozen=True, slots=True)
class SpendingEstimate:
    quantity_scaled: int
    amount_minor: int
    currency: str
    horizon_days: int
    source_date: datetime
    source_quantity_scaled: int
    source_cost_minor: int


@dataclass(frozen=True, slots=True)
class SpendingPeriodBucket:
    day: date
    inventory_purchase_cash_minor: int
    other_expense_cash_minor: int
    known_consumption_value_minor: int


@dataclass(frozen=True, slots=True)
class SpendingCategoryReport:
    label: str
    amount_minor: int


@dataclass(frozen=True, slots=True)
class InventoryItemReport:
    item: InventoryBalance
    insight: InventoryInsight
    cost_summary: InventoryCostSummary
    period_activity: InventoryCostActivity
    lifetime_activity: InventoryCostActivity
    generated_at: datetime
    period_days: int
    period_start: datetime
    period_end: datetime
    currency: str
    period_purchased_quantity_scaled: int
    period_purchase_cash_minor: int
    lifetime_purchased_quantity_scaled: int
    lifetime_purchase_cash_minor: int
    period_used_quantity_scaled: int
    period_consumption_value_minor: int
    period_expiry_value_minor: int
    period_variance_value_minor: int
    lifetime_consumption_value_minor: int
    lifetime_expiry_value_minor: int
    lifetime_variance_value_minor: int
    current_known_value_minor: int
    latest_purchase: PurchaseCurrent | None
    estimate: SpendingEstimate | None
    period_buckets: tuple[SpendingPeriodBucket, ...]
    available: bool
    lag_events: int

    @property
    def known_value_reconciles(self) -> bool:
        return self.lifetime_purchase_cash_minor == (
            self.lifetime_consumption_value_minor
            + self.lifetime_expiry_value_minor
            + self.lifetime_variance_value_minor
            + self.current_known_value_minor
        )

    @property
    def spending_trend_supported(self) -> bool:
        return (
            sum(
                bucket.inventory_purchase_cash_minor > 0 or bucket.known_consumption_value_minor > 0
                for bucket in self.period_buckets
            )
            >= 2
        )


@dataclass(frozen=True, slots=True)
class InventoryCategoryReport:
    code: str
    label: str
    item_count: int
    purchase_cash_minor: int
    consumption_value_minor: int
    current_known_value_minor: int
    estimate_minor: int


@dataclass(frozen=True, slots=True)
class InventoryCollectionReport:
    generated_at: datetime
    period_days: int
    period_start: datetime
    period_end: datetime
    currency: str
    currencies: tuple[str, ...]
    items: tuple[InventoryItemReport, ...]
    categories: tuple[InventoryCategoryReport, ...]
    spending_categories: tuple[SpendingCategoryReport, ...]
    period_buckets: tuple[SpendingPeriodBucket, ...]
    supply_purchase_cash_minor: int
    other_expense_cash_minor: int
    consumption_value_minor: int
    expiry_value_minor: int
    variance_value_minor: int
    current_known_value_minor: int
    unknown_cost_items: int
    unused_items: int
    estimate_minor: int
    reorder_items: int
    check_due_items: int
    available: bool
    lag_events: int

    @property
    def spending_trend_supported(self) -> bool:
        return (
            sum(
                bucket.inventory_purchase_cash_minor > 0 or bucket.other_expense_cash_minor > 0
                for bucket in self.period_buckets
            )
            >= 2
        )

    @property
    def spending_trend_direction(self) -> str:
        midpoint = len(self.period_buckets) // 2
        first = sum(
            bucket.inventory_purchase_cash_minor + bucket.other_expense_cash_minor
            for bucket in self.period_buckets[:midpoint]
        )
        second = sum(
            bucket.inventory_purchase_cash_minor + bucket.other_expense_cash_minor
            for bucket in self.period_buckets[midpoint:]
        )
        if second > first:
            return "increased"
        if second < first:
            return "decreased"
        return "held steady"


class ReportService:
    def __init__(
        self,
        animals: AnimalService,
        expenses: ExpenseService,
        projected_events: ProjectedEventReader | None = None,
        inventory: InventoryService | None = None,
        purchases: PurchaseService | None = None,
        inventory_intelligence: InventoryIntelligenceProjection | None = None,
    ) -> None:
        self._animals = animals
        self._expenses = expenses
        self._projected_events = projected_events
        self._inventory = inventory
        self._purchases = purchases
        self._inventory_intelligence = inventory_intelligence

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
        rows = [
            ReportRow(
                (
                    item.occurred_at.isoformat(timespec="minutes"),
                    "Other expense",
                    item.category,
                    f"{item.amount_minor / 100:.2f}",
                    item.currency,
                    item.status,
                )
            )
            for item in self._expenses.list_expenses(household_id)
        ]
        if self._purchases is not None:
            rows.extend(
                ReportRow(
                    (
                        purchase.occurred_at.isoformat(timespec="minutes"),
                        "Supply purchase",
                        "Inventory",
                        f"{purchase.total_paid_minor / 100:.2f}",
                        purchase.currency,
                        purchase.status,
                    )
                )
                for purchase in self._purchases.list_purchases(household_id)
            )
        rows.sort(key=lambda row: row.values[0], reverse=True)
        return KeeperReport(
            "Spending records",
            ("Occurred", "Source", "Category", "Amount", "Currency", "Status"),
            tuple(rows),
            generated_at,
        )

    def inventory_collection(
        self,
        household_id: UUID,
        *,
        household_timezone: str,
        generated_at: datetime,
        period_days: int,
        currency: str | None = None,
    ) -> InventoryCollectionReport:
        inventory, purchases, intelligence = self._inventory_dependencies()
        period_start, period_end = _report_period(generated_at, household_timezone, period_days)
        items = inventory.list_balances(household_id, status="active")
        purchase_rows = tuple(
            purchase
            for purchase in purchases.list_purchases(household_id)
            if purchase.status == "active"
        )
        other_expenses = tuple(
            expense
            for expense in self._expenses.list_expenses(household_id)
            if expense.status == "active"
        )
        currencies = _available_currencies(purchase_rows, other_expenses)
        selected_currency = _selected_currency(currency, currencies)
        reports = tuple(
            self._inventory_item_report(
                household_id,
                item,
                household_timezone,
                generated_at,
                period_days,
                period_start,
                period_end,
                selected_currency,
                purchase_rows,
                purchases,
                intelligence,
            )
            for item in items
        )
        category_totals: dict[str, list[int]] = {}
        category_labels: dict[str, str] = {}
        for report in reports:
            code = report.item.inventory_type or "needs_setup"
            category_labels[code] = report.item.type_label
            totals = category_totals.setdefault(code, [0, 0, 0, 0, 0])
            totals[0] += 1
            totals[1] += report.period_purchase_cash_minor
            totals[2] += report.period_consumption_value_minor
            totals[3] += report.current_known_value_minor
            totals[4] += report.estimate.amount_minor if report.estimate else 0
        categories = tuple(
            InventoryCategoryReport(code, category_labels[code], *category_totals[code])
            for code in sorted(category_totals, key=lambda value: category_labels[value])
        )
        other_cash = sum(
            expense.amount_minor
            for expense in other_expenses
            if expense.currency == selected_currency
            and period_start <= expense.occurred_at.astimezone(UTC) < period_end
        )
        period_buckets = _collection_period_buckets(
            period_start,
            period_days,
            household_timezone,
            purchase_rows,
            other_expenses,
            reports,
            selected_currency,
        )
        return InventoryCollectionReport(
            generated_at=generated_at,
            period_days=period_days,
            period_start=period_start,
            period_end=period_end,
            currency=selected_currency,
            currencies=currencies,
            items=reports,
            categories=categories,
            spending_categories=_spending_categories(
                categories,
                other_expenses,
                period_start,
                period_end,
                selected_currency,
            ),
            period_buckets=period_buckets,
            supply_purchase_cash_minor=sum(
                purchase.total_paid_minor
                for purchase in purchase_rows
                if purchase.currency == selected_currency
                and period_start <= purchase.occurred_at.astimezone(UTC) < period_end
            ),
            other_expense_cash_minor=other_cash,
            consumption_value_minor=sum(
                report.period_consumption_value_minor for report in reports
            ),
            expiry_value_minor=sum(report.period_expiry_value_minor for report in reports),
            variance_value_minor=sum(report.period_variance_value_minor for report in reports),
            current_known_value_minor=sum(report.current_known_value_minor for report in reports),
            unknown_cost_items=sum(
                report.cost_summary.unknown_remaining_quantity_scaled > 0 for report in reports
            ),
            unused_items=sum(
                report.insight.usage_state in {"no_use_90", "no_use_180"} for report in reports
            ),
            estimate_minor=sum(
                report.estimate.amount_minor for report in reports if report.estimate
            ),
            reorder_items=sum(
                report.insight.reorder_state in {"reorder_now", "reorder_soon"}
                for report in reports
            ),
            check_due_items=sum(
                stock_check_is_due(report.item, report.insight) for report in reports
            ),
            available=all(report.available for report in reports),
            lag_events=max((report.lag_events for report in reports), default=0),
        )

    def inventory_item(
        self,
        household_id: UUID,
        item_id: UUID,
        *,
        household_timezone: str,
        generated_at: datetime,
        period_days: int,
        currency: str | None = None,
    ) -> InventoryItemReport | None:
        inventory, purchases, intelligence = self._inventory_dependencies()
        item = inventory.balance_for(household_id, item_id)
        if item is None:
            return None
        purchase_rows = tuple(
            purchase
            for purchase in purchases.list_purchases(household_id)
            if purchase.status == "active"
        )
        currencies = _available_currencies(
            purchase_rows,
            tuple(
                expense
                for expense in self._expenses.list_expenses(household_id)
                if expense.status == "active"
            ),
        )
        selected_currency = _selected_currency(currency, currencies)
        period_start, period_end = _report_period(generated_at, household_timezone, period_days)
        return self._inventory_item_report(
            household_id,
            item,
            household_timezone,
            generated_at,
            period_days,
            period_start,
            period_end,
            selected_currency,
            purchase_rows,
            purchases,
            intelligence,
        )

    def inventory_collection_csv(self, report: InventoryCollectionReport) -> KeeperReport:
        return KeeperReport(
            "Inventory and spending",
            (
                "Item",
                "Type",
                "Inventory use",
                "On hand",
                f"Purchased quantity ({report.period_days} days)",
                f"Purchase cash {report.currency}",
                f"Used quantity ({report.period_days} days)",
                f"Consumption value {report.currency}",
                f"Current known value {report.currency}",
                "Unknown-cost quantity",
                "Reorder state",
                f"Potential replenishment estimate {report.currency}",
            ),
            tuple(
                ReportRow(
                    (
                        item.item.name,
                        item.item.type_label,
                        item.item.stock_role_label,
                        _format_scaled(item.item.on_hand_quantity_scaled),
                        _format_scaled(item.period_purchased_quantity_scaled),
                        _format_minor(item.period_purchase_cash_minor),
                        _format_scaled(item.period_used_quantity_scaled),
                        _format_minor(item.period_consumption_value_minor),
                        _format_minor(item.current_known_value_minor),
                        _format_scaled(item.cost_summary.unknown_remaining_quantity_scaled),
                        item.insight.reorder_state,
                        _format_minor(item.estimate.amount_minor) if item.estimate else "",
                    )
                )
                for item in report.items
            ),
            report.generated_at,
        )

    def inventory_item_csv(self, report: InventoryItemReport) -> KeeperReport:
        values = (
            ("Item", report.item.name),
            ("Type", report.item.type_label),
            ("Inventory use", report.item.stock_role_label),
            ("Unit", report.item.unit_label),
            ("On hand", _format_scaled(report.item.on_hand_quantity_scaled)),
            ("Period days", str(report.period_days)),
            ("Currency", report.currency),
            ("Period purchased quantity", _format_scaled(report.period_purchased_quantity_scaled)),
            ("Period purchase cash", _format_minor(report.period_purchase_cash_minor)),
            ("Period used quantity", _format_scaled(report.period_used_quantity_scaled)),
            ("Period consumption value", _format_minor(report.period_consumption_value_minor)),
            ("Period expiry value", _format_minor(report.period_expiry_value_minor)),
            ("Period variance value", _format_minor(report.period_variance_value_minor)),
            ("Current known stock value", _format_minor(report.current_known_value_minor)),
            (
                "Current unknown-cost quantity",
                _format_scaled(report.cost_summary.unknown_remaining_quantity_scaled),
            ),
            ("Reorder state", report.insight.reorder_state),
            (
                "Potential replenishment estimate",
                _format_minor(report.estimate.amount_minor) if report.estimate else "",
            ),
            ("Generated at", report.generated_at.isoformat()),
        )
        return KeeperReport(
            f"{report.item.name} inventory report",
            ("Measure", "Value"),
            tuple(ReportRow(row) for row in values),
            report.generated_at,
        )

    def _inventory_dependencies(
        self,
    ) -> tuple[InventoryService, PurchaseService, InventoryIntelligenceProjection]:
        if (
            self._inventory is None
            or self._purchases is None
            or self._inventory_intelligence is None
        ):
            raise RuntimeError("Inventory reporting is not configured.")
        return self._inventory, self._purchases, self._inventory_intelligence

    def _inventory_item_report(
        self,
        household_id: UUID,
        item: InventoryBalance,
        household_timezone: str,
        generated_at: datetime,
        period_days: int,
        period_start: datetime,
        period_end: datetime,
        currency: str,
        purchase_rows: tuple[PurchaseCurrent, ...],
        purchases: PurchaseService,
        intelligence: InventoryIntelligenceProjection,
    ) -> InventoryItemReport:
        item_purchases = tuple(
            (purchase, line)
            for purchase in purchase_rows
            if purchase.currency == currency
            for line in purchase.lines
            if line.status == "active" and line.inventory_item_id == item.item_id
        )
        period_purchases = tuple(
            (purchase, line)
            for purchase, line in item_purchases
            if period_start <= purchase.occurred_at.astimezone(UTC) < period_end
        )
        insight = intelligence.insight_for(
            household_id, item.item_id, household_timezone, generated_at
        )
        cost_summary = purchases.cost_summary_for(household_id, item.item_id)
        period_activity = purchases.cost_activity_for(
            household_id, item.item_id, period_start, period_end
        )
        period_activity_points = purchases.cost_activity_points_for(
            household_id, item.item_id, period_start, period_end
        )
        lifetime_activity = purchases.cost_activity_for(
            household_id,
            item.item_id,
            datetime(1970, 1, 1, tzinfo=UTC),
            generated_at,
        )
        latest = max(
            (purchase for purchase, _line in item_purchases),
            key=lambda purchase: (purchase.occurred_at, str(purchase.purchase_id)),
            default=None,
        )
        estimate = _spending_estimate(
            item,
            insight,
            item_purchases,
            period_days,
            currency,
            generated_at,
        )
        return InventoryItemReport(
            item=item,
            insight=insight,
            cost_summary=cost_summary,
            period_activity=period_activity,
            lifetime_activity=lifetime_activity,
            generated_at=generated_at,
            period_days=period_days,
            period_start=period_start,
            period_end=period_end,
            currency=currency,
            period_purchased_quantity_scaled=sum(
                line.quantity_scaled for _purchase, line in period_purchases
            ),
            period_purchase_cash_minor=sum(
                line.allocated_cost_minor for _purchase, line in period_purchases
            ),
            lifetime_purchased_quantity_scaled=sum(
                line.quantity_scaled for _purchase, line in item_purchases
            ),
            lifetime_purchase_cash_minor=sum(
                line.allocated_cost_minor for _purchase, line in item_purchases
            ),
            period_used_quantity_scaled=(
                insight.used_30_scaled if period_days == 30 else insight.used_90_scaled
            ),
            period_consumption_value_minor=_currency_amount(
                period_activity.known_consumed, currency
            ),
            period_expiry_value_minor=_currency_amount(period_activity.known_expired, currency),
            period_variance_value_minor=_currency_amount(period_activity.known_variance, currency),
            lifetime_consumption_value_minor=_currency_amount(
                lifetime_activity.known_consumed, currency
            ),
            lifetime_expiry_value_minor=_currency_amount(lifetime_activity.known_expired, currency),
            lifetime_variance_value_minor=_currency_amount(
                lifetime_activity.known_variance, currency
            ),
            current_known_value_minor=_currency_amount(cost_summary.known_remaining, currency),
            latest_purchase=latest,
            estimate=estimate,
            period_buckets=_item_period_buckets(
                period_start,
                period_days,
                household_timezone,
                period_purchases,
                period_activity_points,
                currency,
            ),
            available=(
                insight.available
                and cost_summary.available
                and period_activity.available
                and lifetime_activity.available
            ),
            lag_events=max(
                insight.lag_events,
                cost_summary.lag_events,
                period_activity.lag_events,
                lifetime_activity.lag_events,
            ),
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


def _report_period(
    generated_at: datetime, household_timezone: str, period_days: int
) -> tuple[datetime, datetime]:
    if period_days not in {30, 90}:
        raise ValueError("Inventory report period must be 30 or 90 days.")
    zone = ZoneInfo(household_timezone)
    end_date = generated_at.astimezone(zone).date()
    end_local = datetime.combine(end_date, time.min, tzinfo=zone)
    return (end_local - timedelta(days=period_days)).astimezone(UTC), end_local.astimezone(UTC)


def _available_currencies(
    purchases: tuple[PurchaseCurrent, ...], expenses: tuple[object, ...]
) -> tuple[str, ...]:
    values = {purchase.currency for purchase in purchases}
    values.update(
        str(currency)
        for expense in expenses
        if (currency := getattr(expense, "currency", None)) is not None
    )
    return tuple(sorted(values)) or ("USD",)


def _selected_currency(requested: str | None, currencies: tuple[str, ...]) -> str:
    normalized = requested.strip().upper() if requested else None
    if normalized is not None and normalized not in currencies:
        raise ValueError("Choose a currency represented in this household's spending records.")
    return normalized or currencies[0]


def _currency_amount(values: tuple[CurrencyValue, ...], currency: str) -> int:
    return next((value.amount_minor for value in values if value.currency == currency), 0)


def _blank_period_buckets(
    period_start: datetime, period_days: int, household_timezone: str
) -> dict[date, list[int]]:
    first_day = period_start.astimezone(ZoneInfo(household_timezone)).date()
    return {first_day + timedelta(days=offset): [0, 0, 0] for offset in range(period_days)}


def _item_period_buckets(
    period_start: datetime,
    period_days: int,
    household_timezone: str,
    purchases: tuple[tuple[PurchaseCurrent, PurchaseLineCurrent], ...],
    activity_points: tuple[InventoryCostActivityPoint, ...],
    currency: str,
) -> tuple[SpendingPeriodBucket, ...]:
    zone = ZoneInfo(household_timezone)
    values = _blank_period_buckets(period_start, period_days, household_timezone)
    for purchase, line in purchases:
        bucket = values.get(purchase.occurred_at.astimezone(zone).date())
        if bucket is not None and purchase.currency == currency:
            bucket[0] += line.allocated_cost_minor
    for point in activity_points:
        bucket = values.get(point.occurred_at.astimezone(zone).date())
        if (
            bucket is not None
            and point.currency == currency
            and point.classification == "consumption"
        ):
            bucket[2] += point.amount_minor
    return tuple(SpendingPeriodBucket(day, *amounts) for day, amounts in values.items())


def _collection_period_buckets(
    period_start: datetime,
    period_days: int,
    household_timezone: str,
    purchases: tuple[PurchaseCurrent, ...],
    expenses: tuple[ExpenseCurrent, ...],
    item_reports: tuple[InventoryItemReport, ...],
    currency: str,
) -> tuple[SpendingPeriodBucket, ...]:
    zone = ZoneInfo(household_timezone)
    values = _blank_period_buckets(period_start, period_days, household_timezone)
    for purchase in purchases:
        bucket = values.get(purchase.occurred_at.astimezone(zone).date())
        if bucket is not None and purchase.currency == currency:
            bucket[0] += purchase.total_paid_minor
    for expense in expenses:
        bucket = values.get(expense.occurred_at.astimezone(zone).date())
        if bucket is not None and expense.currency == currency:
            bucket[1] += expense.amount_minor
    for report in item_reports:
        for point in report.period_buckets:
            values[point.day][2] += point.known_consumption_value_minor
    return tuple(SpendingPeriodBucket(day, *amounts) for day, amounts in values.items())


def _spending_categories(
    inventory_categories: tuple[InventoryCategoryReport, ...],
    expenses: tuple[ExpenseCurrent, ...],
    period_start: datetime,
    period_end: datetime,
    currency: str,
) -> tuple[SpendingCategoryReport, ...]:
    totals = {
        category.label: category.purchase_cash_minor
        for category in inventory_categories
        if category.purchase_cash_minor > 0
    }
    for expense in expenses:
        if (
            expense.currency != currency
            or not period_start <= expense.occurred_at.astimezone(UTC) < period_end
        ):
            continue
        category = expense.category.replace("_", " ").strip().title() or "Other"
        label = f"Other expenses · {category}"
        totals[label] = totals.get(label, 0) + expense.amount_minor
    return tuple(
        SpendingCategoryReport(label, amount)
        for label, amount in sorted(totals.items(), key=lambda value: (-value[1], value[0]))
    )


def _format_scaled(value: int) -> str:
    decimal = Decimal(value) / Decimal(1000)
    return format(decimal.normalize(), "f") if decimal else "0"


def _format_minor(value: int) -> str:
    return f"{Decimal(value) / Decimal(100):.2f}"


def _spending_estimate(
    item: InventoryBalance,
    insight: InventoryInsight,
    item_purchases: tuple[tuple[PurchaseCurrent, PurchaseLineCurrent], ...],
    horizon_days: int,
    currency: str,
    as_of: datetime,
) -> SpendingEstimate | None:
    if (
        item.stock_role != "care_supply"
        or not insight.available
        or insight.daily_rate_scaled is None
        or insight.daily_rate_scaled <= 0
    ):
        return None
    priced = tuple(
        (purchase, line)
        for purchase, line in item_purchases
        if line.quantity_scaled > 0
        and line.allocated_cost_minor > 0
        and purchase.currency == currency
        and as_of - timedelta(days=365) <= purchase.occurred_at <= as_of
    )
    if not priced:
        return None
    latest_purchase, latest_line = max(
        priced,
        key=lambda value: (
            value[0].occurred_at,
            str(value[0].purchase_id),
            str(value[1].purchase_line_id),
        ),
    )
    horizon_use = int(
        (insight.daily_rate_scaled * Decimal(horizon_days)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    desired_remaining = item.target_quantity_scaled or item.reorder_threshold_scaled or 0
    quantity = max(0, horizon_use + desired_remaining - item.available_quantity_scaled)
    if quantity == 0:
        return None
    source_quantity = latest_line.quantity_scaled
    source_cost = latest_line.allocated_cost_minor
    amount = (quantity * source_cost + source_quantity - 1) // source_quantity
    return SpendingEstimate(
        quantity,
        amount,
        currency,
        horizon_days,
        latest_purchase.occurred_at,
        source_quantity,
        source_cost,
    )
