"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const dashboard = document.querySelector("[data-report-dashboard]");
  if (!dashboard || !window.Chart) return;

  let payload;
  try {
    payload = JSON.parse(dashboard.dataset.reportPayload || "{}");
  } catch (_error) {
    return;
  }

  const currency = payload.currency || "USD";
  const money = (minor) => new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number(minor) / 100);
  const palette = {
    violet: "#a78bfa",
    blue: "#75b9ff",
    green: "#66d6a3",
    gold: "#f3bd5b",
    coral: "#ff7d8b",
    grid: "rgba(146, 137, 159, .18)",
    text: "#c8c1d2",
  };
  const moneyScale = {
    beginAtZero: true,
    grid: {color: palette.grid},
    ticks: {color: palette.text, callback: (value) => money(value)},
  };
  const legend = {
    position: "bottom",
    labels: {color: palette.text, usePointStyle: true, padding: 18},
  };
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: {mode: "index", intersect: false},
    plugins: {
      legend,
      tooltip: {callbacks: {label: (context) => `${context.dataset.label}: ${money(context.raw)}`}},
    },
  };
  const buckets = payload.buckets || [];

  const render = (kind, configuration) => {
    const canvas = dashboard.querySelector(`[data-report-chart="${kind}"]`);
    if (!canvas) return;
    new window.Chart(canvas, configuration);
  };

  render("spending-trend", {
    type: "line",
    data: {
      labels: buckets.map((bucket) => bucket.label),
      datasets: [
        {
          label: "Inventory purchases",
          data: buckets.map((bucket) => bucket.inventory_purchase_cash_minor),
          borderColor: palette.violet,
          backgroundColor: "rgba(167, 139, 250, .18)",
          borderWidth: 3,
          pointStyle: "circle",
          pointRadius: 2,
          tension: .28,
          fill: true,
        },
        {
          label: "Other expenses",
          data: buckets.map((bucket) => bucket.other_expense_cash_minor),
          borderColor: palette.gold,
          backgroundColor: "rgba(243, 189, 91, .12)",
          borderDash: [7, 4],
          borderWidth: 3,
          pointStyle: "rectRot",
          pointRadius: 2,
          tension: .28,
          fill: true,
        },
      ],
    },
    options: {
      ...baseOptions,
      scales: {
        x: {grid: {display: false}, ticks: {color: palette.text, maxTicksLimit: payload.period_days === 90 ? 10 : 8}},
        y: moneyScale,
      },
    },
  });

  const spendingCategories = payload.spending_categories || [];
  const categoryCanvas = dashboard.querySelector('[data-report-chart="spending-category"]');
  if (categoryCanvas) {
    categoryCanvas.parentElement.style.height = `${Math.max(240, spendingCategories.length * 46)}px`;
  }
  render("spending-category", {
    type: "bar",
    data: {
      labels: spendingCategories.map((category) => category.label),
      datasets: [{
        label: "Amount spent",
        data: spendingCategories.map((category) => category.amount_minor),
        backgroundColor: "rgba(117, 185, 255, .72)",
        borderColor: palette.blue,
        borderWidth: 1,
      }],
    },
    options: {
      ...baseOptions,
      indexAxis: "y",
      plugins: {...baseOptions.plugins, legend: {display: false}},
      scales: {x: moneyScale, y: {grid: {display: false}, ticks: {color: palette.text}}},
    },
  });

  const comparison = payload.bought_vs_used || {};
  render("bought-used", {
    type: "bar",
    data: {
      labels: ["Selected period"],
      datasets: [
        {
          label: "Cash spent on supplies",
          data: [comparison.cash_spent_minor || 0],
          backgroundColor: "rgba(167, 139, 250, .7)",
          borderColor: palette.violet,
          borderWidth: 1,
        },
        {
          label: "Known value actually used",
          data: [comparison.known_value_used_minor || 0],
          backgroundColor: "rgba(102, 214, 163, .7)",
          borderColor: palette.green,
          borderWidth: 1,
        },
      ],
    },
    options: {...baseOptions, scales: {x: {grid: {display: false}, ticks: {color: palette.text}}, y: moneyScale}},
  });

  const stockCategories = payload.stock_categories || [];
  const stockCanvas = dashboard.querySelector('[data-report-chart="stock-value"]');
  if (stockCanvas) {
    stockCanvas.parentElement.style.height = `${Math.max(240, stockCategories.length * 46)}px`;
  }
  render("stock-value", {
    type: "bar",
    data: {
      labels: stockCategories.map((category) => category.label),
      datasets: [{
        label: "Known stock value",
        data: stockCategories.map((category) => category.amount_minor),
        backgroundColor: "rgba(102, 214, 163, .68)",
        borderColor: palette.green,
        borderWidth: 1,
      }],
    },
    options: {
      ...baseOptions,
      indexAxis: "y",
      plugins: {...baseOptions.plugins, legend: {display: false}},
      scales: {x: moneyScale, y: {grid: {display: false}, ticks: {color: palette.text}}},
    },
  });

  render("item-bought-used", {
    type: "line",
    data: {
      labels: buckets.map((bucket) => bucket.label),
      datasets: [
        {
          label: "Purchase cash",
          data: buckets.map((bucket) => bucket.inventory_purchase_cash_minor),
          borderColor: palette.violet,
          backgroundColor: "rgba(167, 139, 250, .14)",
          borderWidth: 3,
          pointStyle: "circle",
          pointRadius: 2,
          tension: .28,
        },
        {
          label: "Known value used",
          data: buckets.map((bucket) => bucket.known_consumption_value_minor),
          borderColor: palette.green,
          backgroundColor: "rgba(102, 214, 163, .12)",
          borderDash: [7, 4],
          borderWidth: 3,
          pointStyle: "rectRot",
          pointRadius: 2,
          tension: .28,
        },
      ],
    },
    options: {
      ...baseOptions,
      scales: {
        x: {grid: {display: false}, ticks: {color: palette.text, maxTicksLimit: payload.period_days === 90 ? 10 : 8}},
        y: moneyScale,
      },
    },
  });
});
