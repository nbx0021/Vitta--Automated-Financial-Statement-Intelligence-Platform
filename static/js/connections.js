/**
 * connections.js
 * ==============
 * Connected Statements Animation Engine for Vitta.
 *
 * Draws animated dashed SVG curved lines between highlighted rows
 * across the 4 financial statement cards.  All positions are computed
 * dynamically via getBoundingClientRect so they work with real data
 * at any layout size.
 *
 * Architecture:
 *   - CONNECTIONS map: connection name → array of element IDs to highlight
 *   - showConnection(name): highlights rows + draws SVG paths
 *   - clearConnection(): removes all highlights + SVG paths
 *   - ResizeObserver: redraws on layout changes
 */

(function () {
  "use strict";

  // ── Connection definitions ─────────────────────────────────────────────────
  // Each key maps to an array of { id, card } objects.
  // The SVG lines are drawn in the ORDER of this array.
  const CONNECTIONS = {
    net_income: {
      caption: "Net Income flows from the bottom of the Income Statement into the top of the Cash Flow Statement as the starting point of the indirect method, and simultaneously increases Retained Earnings in the Equity statement.",
      ids: ["is-ni", "cfs-ni", "scse-net-income"],
      color: "#6366F1",
    },
    depreciation: {
      caption: "Depreciation & Amortization (D&A) is a non-cash charge on the Income Statement — it is added back on the Cash Flow Statement (operating section) because it reduced reported income but required no actual cash outflow.",
      ids: ["is-da-label", "cfs-da"],
      color: "#06B6D4",
    },
    working_cap: {
      caption: "Changes in Working Capital (Accounts Receivable and Accounts Payable on the Balance Sheet) are reflected as adjustments in the Operating Cash Flow section — a rise in AR uses cash, while a rise in AP frees cash.",
      ids: ["bs-ar", "bs-ap", "cfs-wc"],
      color: "#10B981",
    },
    dividends: {
      caption: "Dividends paid appear as a cash outflow in the Financing Activities section of the Cash Flow Statement and reduce Retained Earnings in the Statement of Changes in Equity.",
      ids: ["cfs-div", "scse-div", "bs-retained"],
      color: "#F59E0B",
    },
    cash_tieout: {
      caption: "The Ending Cash Balance on the Cash Flow Statement should exactly equal the Cash & Cash Equivalents line on the Balance Sheet for the same period — this is the fundamental cash tie-out check.",
      ids: ["cfs-cash", "bs-cash"],
      color: "#EF4444",
    },
  };

  // ── State ─────────────────────────────────────────────────────────────────
  let activeConnection = null;

  // ── DOM references ────────────────────────────────────────────────────────
  const svgEl     = document.getElementById("connectionSvg");
  const wrapper   = document.getElementById("statementsGridWrapper");
  const captionEl = document.getElementById("connCaption");

  if (!svgEl || !wrapper) return; // not on the dashboard page

  // ── Core: clear all highlights and SVG lines ──────────────────────────────
  function clearConnection() {
    // Remove row highlights
    document.querySelectorAll(".stmt-row.highlighted").forEach(function (el) {
      el.classList.remove("highlighted");
    });
    // Clear SVG
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
    // Reset caption
    if (captionEl) {
      captionEl.textContent =
        "Select a linkage type above to see how numbers flow between the financial statements.";
      captionEl.classList.remove("active");
    }
    // Reset buttons
    document.querySelectorAll(".conn-btn").forEach(function (btn) {
      btn.classList.remove("active");
    });
  }

  // ── Get center-right or center-left point of an element ──────────────────
  // Returns {x, y} relative to wrapper's top-left.

  function getCenter(el) {
    if (!el) return null;
    const elRect      = el.getBoundingClientRect();
    const wrapRect    = wrapper.getBoundingClientRect();
    const cx = (elRect.left + elRect.right) / 2 - wrapRect.left;
    const cy = (elRect.top + elRect.bottom) / 2 - wrapRect.top;
    return { x: cx, y: cy, left: elRect.left - wrapRect.left, right: elRect.right - wrapRect.left };
  }

  // ── Build a cubic bezier path between two points ──────────────────────────
  function cubicPath(from, to, color) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const absDx = Math.abs(dx);
    const cpOffset = Math.max(absDx * 0.55, 60);

    let d;
    if (Math.abs(dy) < 30) {
      // Horizontal-ish: bow up or down a little
      const bowing = (from.x < to.x) ? -50 : 50;
      d = `M ${from.x} ${from.y} C ${from.x + cpOffset} ${from.y + bowing} ${to.x - cpOffset} ${to.y + bowing} ${to.x} ${to.y}`;
    } else {
      d = `M ${from.x} ${from.y} C ${from.x + cpOffset} ${from.y} ${to.x - cpOffset} ${to.y} ${to.x} ${to.y}`;
    }

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("class", "conn-path");
    path.setAttribute("stroke", color);

    return path;
  }

  // ── Add endpoint dots ─────────────────────────────────────────────────────
  function addDot(x, y, color) {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("r", 5);
    circle.setAttribute("class", "conn-dot");
    circle.setAttribute("fill", color);
    svgEl.appendChild(circle);
  }

  // ── Resize the SVG to match the wrapper ───────────────────────────────────
  function resizeSvg() {
    const rect = wrapper.getBoundingClientRect();
    svgEl.setAttribute("width",  rect.width);
    svgEl.setAttribute("height", rect.height);
    svgEl.setAttribute("viewBox", `0 0 ${rect.width} ${rect.height}`);
  }

  // ── Main: draw connection ─────────────────────────────────────────────────
  function drawConnection(connName) {
    const conn = CONNECTIONS[connName];
    if (!conn) return;

    clearConnection();
    resizeSvg();

    activeConnection = connName;

    // Highlight button
    const btnMap = {
      net_income:   "connBtnNI",
      depreciation: "connBtnDA",
      working_cap:  "connBtnWC",
      dividends:    "connBtnDiv",
      cash_tieout:  "connBtnCash",
    };
    const btnEl = document.getElementById(btnMap[connName]);
    if (btnEl) btnEl.classList.add("active");

    // Update caption
    if (captionEl) {
      captionEl.textContent = conn.caption;
      captionEl.classList.add("active");
    }

    // Collect all valid highlighted elements
    const points = [];

    conn.ids.forEach(function (id) {
      const el = document.getElementById(id);
      if (!el) return;

      el.classList.add("highlighted");

      const center = getCenter(el);
      if (center) {
        points.push({ el, center, id });
      }
    });

    // Draw paths between consecutive points
    for (let i = 0; i < points.length - 1; i++) {
      const from = points[i];
      const to   = points[i + 1];

      // Decide which edges to connect from/to
      // Use right edge of "from" and left edge of "to" if they're in different columns
      const fromX = (from.center.x < to.center.x)
        ? from.center.right
        : from.center.left;
      const toX = (from.center.x < to.center.x)
        ? to.center.left
        : to.center.right;

      const fromPt = { x: fromX, y: from.center.y };
      const toPt   = { x: toX,   y: to.center.y };

      const path = cubicPath(fromPt, toPt, conn.color);
      svgEl.appendChild(path);

      // Endpoint dots
      addDot(fromPt.x, fromPt.y, conn.color);
      if (i === points.length - 2) {
        addDot(toPt.x, toPt.y, conn.color);
      }
    }

    // If only one point (element not found for others), still highlight it
  }

  // ── Public API ────────────────────────────────────────────────────────────
  window.showConnection = function (connName) {
    if (activeConnection === connName) {
      // Toggle off
      clearConnection();
      activeConnection = null;
      return;
    }
    drawConnection(connName);
  };

  // ── Resize handling ───────────────────────────────────────────────────────
  function onResize() {
    resizeSvg();
    if (activeConnection) {
      // Redraw connection at new positions
      const connName = activeConnection;
      activeConnection = null; // prevent toggle
      drawConnection(connName);
    }
  }

  // Use ResizeObserver for precise element resize tracking
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(function () {
      // Debounce slightly to avoid rapid redraws during animation
      clearTimeout(window._vittaResizeTimer);
      window._vittaResizeTimer = setTimeout(onResize, 60);
    });
    ro.observe(wrapper);
  } else {
    window.addEventListener("resize", function () {
      clearTimeout(window._vittaResizeTimer);
      window._vittaResizeTimer = setTimeout(onResize, 100);
    });
  }

  // ── Initialize SVG dimensions ─────────────────────────────────────────────
  // Wait a tick for layout to settle before measuring
  requestAnimationFrame(function () {
    resizeSvg();
  });

})();
