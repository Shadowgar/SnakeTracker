"use strict";

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("canvas[data-chart-endpoint]").forEach(async (canvas) => {
    const response = await fetch(canvas.dataset.chartEndpoint, {credentials: "same-origin"});
    if (!response.ok) return;
    const payload = await response.json();
    const groups = new Map();
    payload.points.forEach((point) => {
      if (!groups.has(point.kind)) groups.set(point.kind, []);
      groups.get(point.kind).push({x: point.occurred_at, y: point.value});
    });
    const colors = ["#b8e65c", "#79b8ff"];
    new window.Chart(canvas, {
      type: "line",
      data: {datasets: Array.from(groups, ([label, data], index) => ({label, data, borderColor: colors[index % colors.length], backgroundColor: colors[index % colors.length]}))},
      options: {responsive: true, parsing: false, scales: {x: {type: "category"}}, plugins: {legend: {labels: {color: "#f4f7f2"}}}}
    });
  });
});
