/**
 * dashboard.js
 * ============
 * Chart.js initialization for the Vitta dashboard.
 * Reads data from the embedded JSON script tag.
 */

(function () {
  "use strict";

  // ── Parse server data ──────────────────────────────────────────────────────
  const raw = document.getElementById("vittaData");
  if (!raw) return;

  let data;
  try {
    data = JSON.parse(raw.textContent);
  } catch (e) {
    console.error("Vitta: failed to parse chart data", e);
    return;
  }

  const {
    chartLabels = [],
    chartRevenue = [],
    chartNetIncome = [],
    chartAssets = [],
    chartLiabilities = [],
  } = data;

  // ── Chart.js global defaults ───────────────────────────────────────────────
  Chart.defaults.color = "#94A3B8";
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.font.size = 12;

  // ── Color helpers ──────────────────────────────────────────────────────────
  const ACCENT       = "#6366F1";
  const ACCENT2      = "#06B6D4";
  const ACCENT_ALPHA = "rgba(99,102,241,0.15)";
  const ACCENT2_ALPHA= "rgba(6,182,212,0.12)";
  const GREEN        = "#10B981";
  const RED          = "#EF4444";

  function gradientFill(ctx, color1, color2) {
    const gradient = ctx.createLinearGradient(0, 0, 0, 280);
    gradient.addColorStop(0, color1);
    gradient.addColorStop(1, color2);
    return gradient;
  }

  // ── Shared chart options ───────────────────────────────────────────────────
  function baseOptions(yLabel = "₹ Crore") {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          labels: {
            usePointStyle: true,
            pointStyle: "circle",
            padding: 20,
            color: "#CBD5E1",
            font: { size: 12, weight: "500" },
          },
        },
        tooltip: {
          backgroundColor: "rgba(15,23,42,0.95)",
          borderColor: "#2D3B52",
          borderWidth: 1,
          padding: 12,
          titleColor: "#F1F5F9",
          bodyColor: "#CBD5E1",
          callbacks: {
            label: function (ctx) {
              const v = ctx.parsed.y;
              if (v === null || v === undefined) return " —";
              const abs = Math.abs(v);
              let s;
              if (abs >= 1000) {
                s = "₹ " + (v / 1000).toFixed(1) + "K Cr";
              } else {
                s = "₹ " + v.toFixed(1) + " Cr";
              }
              return " " + ctx.dataset.label + ": " + s;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(45,59,82,0.5)", drawBorder: false },
          ticks: { color: "#64748B" },
        },
        y: {
          grid: { color: "rgba(45,59,82,0.5)", drawBorder: false },
          ticks: {
            color: "#64748B",
            callback: function (val) {
              const abs = Math.abs(val);
              if (abs >= 1000) return "₹" + (val / 1000).toFixed(0) + "K";
              return "₹" + val.toFixed(0);
            },
          },
          title: {
            display: true,
            text: yLabel,
            color: "#64748B",
            font: { size: 11 },
          },
        },
      },
    };
  }

  // ── Revenue vs Net Income Chart ────────────────────────────────────────────
  const ctxRevNI = document.getElementById("chartRevNI");
  let chartRevNI = null;

  if (ctxRevNI) {
    const ctx = ctxRevNI.getContext("2d");

    chartRevNI = new Chart(ctx, {
      type: "bar",
      data: {
        labels: chartLabels,
        datasets: [
          {
            label: "Revenue",
            data: chartRevenue,
            backgroundColor: function (context) {
              const chart = context.chart;
              const { ctx, chartArea } = chart;
              if (!chartArea) return ACCENT_ALPHA;
              return gradientFill(ctx, "rgba(99,102,241,0.7)", "rgba(99,102,241,0.15)");
            },
            borderColor: ACCENT,
            borderWidth: 1.5,
            borderRadius: 6,
            borderSkipped: false,
          },
          {
            label: "Net Income",
            data: chartNetIncome,
            backgroundColor: function (context) {
              const chart = context.chart;
              const { ctx, chartArea } = chart;
              if (!chartArea) return ACCENT2_ALPHA;
              return gradientFill(ctx, "rgba(6,182,212,0.65)", "rgba(6,182,212,0.12)");
            },
            borderColor: ACCENT2,
            borderWidth: 1.5,
            borderRadius: 6,
            borderSkipped: false,
          },
        ],
      },
      options: {
        ...baseOptions("₹ Crore"),
        animation: {
          duration: 900,
          easing: "easeInOutQuart",
        },
      },
    });
  }

  // ── Assets vs Liabilities Chart ───────────────────────────────────────────
  const ctxAL = document.getElementById("chartAssetsLiab");
  let chartAL = null;

  if (ctxAL) {
    const ctx = ctxAL.getContext("2d");

    chartAL = new Chart(ctx, {
      type: "line",
      data: {
        labels: chartLabels,
        datasets: [
          {
            label: "Total Assets",
            data: chartAssets,
            borderColor: GREEN,
            backgroundColor: "rgba(16,185,129,0.08)",
            borderWidth: 2.5,
            pointBackgroundColor: GREEN,
            pointRadius: 4,
            pointHoverRadius: 7,
            fill: true,
            tension: 0.35,
          },
          {
            label: "Total Liabilities",
            data: chartLiabilities,
            borderColor: RED,
            backgroundColor: "rgba(239,68,68,0.06)",
            borderWidth: 2.5,
            pointBackgroundColor: RED,
            pointRadius: 4,
            pointHoverRadius: 7,
            fill: true,
            tension: 0.35,
          },
        ],
      },
      options: {
        ...baseOptions("₹ Crore"),
        animation: { duration: 900, easing: "easeInOutQuart" },
      },
    });
  }

  // ── Chart tab switching ────────────────────────────────────────────────────
  window.switchChart = function (which) {
    const tabRevNI     = document.getElementById("tabRevNI");
    const tabAssetsLiab = document.getElementById("tabAssetsLiab");
    const canvasRevNI  = document.getElementById("chartRevNI");
    const canvasAL     = document.getElementById("chartAssetsLiab");

    if (which === "revni") {
      canvasRevNI.classList.remove("hidden");
      canvasAL.classList.add("hidden");
      tabRevNI.classList.add("active");
      tabAssetsLiab.classList.remove("active");
      if (chartRevNI) chartRevNI.update();
    } else {
      canvasAL.classList.remove("hidden");
      canvasRevNI.classList.add("hidden");
      tabAssetsLiab.classList.add("active");
      tabRevNI.classList.remove("active");
      if (chartAL) chartAL.update();
    }
  };
})();
