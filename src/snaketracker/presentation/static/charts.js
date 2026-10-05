"use strict";

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("canvas[data-chart-endpoint]").forEach(async (canvas) => {
    const response = await fetch(canvas.dataset.chartEndpoint, {credentials: "same-origin"});
    if (!response.ok) return;
    const payload = await response.json();
    const groups = new Map();
    payload.points.forEach((point) => {
      const key = `${point.kind}:${point.unit}`;
      if (!groups.has(key)) groups.set(key, {kind: point.kind, unit: point.unit, points: []});
      groups.get(key).points.push({x: point.occurred_at, y: point.value,
        entered: `${point.display_value ?? point.value} ${point.display_unit ?? point.unit}`});
    });
    const colors = ["#a78bfa", "#75b9ff"];
    const scales = {x: {type: "category", ticks: {color: "#92899f"}, grid: {color: "#292335"}}};
    const datasets = Array.from(groups, ([key, group], index) => {
      const axis = `measurement-${key}`;
      scales[axis] = {type: "linear", position: index === 0 ? "left" : "right",
        title: {display: true, text: `${group.kind === "length" ? "Length" : "Weight"} (${group.unit})`, color: "#f6f3fb"},
        ticks: {color: "#92899f"}, grid: {color: "#292335", drawOnChartArea: index === 0}};
      return {label: `${group.kind} (${group.unit})`, data: group.points, yAxisID: axis,
        borderColor: colors[index % colors.length], backgroundColor: colors[index % colors.length]};
    });
    new window.Chart(canvas, {
      type: "line", data: {datasets},
      options: {responsive: true, maintainAspectRatio: false, parsing: false, scales,
        plugins: {legend: {labels: {color: "#f6f3fb"}}, tooltip: {callbacks: {
          label: (context) => `${context.dataset.label}: ${context.parsed.y}; recorded ${context.raw.entered}`
        }}}}
    });
  });
});
