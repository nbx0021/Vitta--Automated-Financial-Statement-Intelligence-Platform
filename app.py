"""
app.py
======
Vitta — Automated Financial Statement Intelligence Platform
Flask entry point, routes, and pipeline orchestration.

Run with: python app.py
"""
from __future__ import annotations

import logging
import os
from datetime import date

from flask import Flask, abort, redirect, render_template, request, send_file, url_for
from flask_caching import Cache

from data.fetcher import get_all_data
from data.narrative import build_narrative
from data.sectors import compute_ratios
from data.transform import normalize_financials, series_to_list
from data.validation import run_all_checks
from reports.generator import generate_pdf

import io

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = 300  # 5 minutes
cache = Cache(app)


# ---------------------------------------------------------------------------
# Ticker normalization
# ---------------------------------------------------------------------------

def normalize_ticker(raw: str) -> str:
    """Ensure ticker is uppercase and ends with .NS."""
    t = raw.strip().upper()
    if not t.endswith(".NS"):
        t = t + ".NS"
    return t


# ---------------------------------------------------------------------------
# Pipeline (cached per ticker)
# ---------------------------------------------------------------------------

@cache.memoize(timeout=300)
def run_pipeline(ticker: str) -> dict:
    """
    Run the full Vitta data pipeline for a ticker.
    Returns a dict with all data needed by both the dashboard and the PDF.
    Raises ValueError on bad ticker / no data returned.
    """
    logger.info("Running pipeline for %s", ticker)

    raw = get_all_data(ticker)
    info = raw.get("info", {})

    # Validate that we got at least some useful data
    inc = raw.get("income")
    bal = raw.get("balance")
    cfs = raw.get("cashflow")

    if (inc is None or inc.empty) and (bal is None or bal.empty):
        raise ValueError(
            f"No financial data returned for '{ticker}'. "
            "Please verify the ticker is a valid NSE symbol (e.g. TCS.NS)."
        )

    normalized = normalize_financials(raw)
    checks = run_all_checks(normalized)
    ratios = compute_ratios(normalized, info)
    periods = normalized.get("periods", [])

    company_name = (
        info.get("longName")
        or info.get("shortName")
        or ticker
    )

    narrative = build_narrative(normalized, ratios, checks, company_name, periods)

    return {
        "ticker": ticker,
        "company_name": company_name,
        "info": info,
        "normalized": normalized,
        "checks": checks,
        "ratios": ratios,
        "periods": periods,
        "narrative": narrative,
        "as_of": date.today().strftime("%d %B %Y"),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["GET", "POST"])
def analyze_form():
    """Handle form submission from the index page."""
    ticker_raw = request.values.get("ticker", "").strip()
    if not ticker_raw:
        return render_template("index.html", error="Please enter an NSE ticker symbol.")
    ticker = normalize_ticker(ticker_raw)
    return redirect(url_for("analyze", ticker=ticker))


@app.route("/analyze/<ticker>")
def analyze(ticker: str):
    ticker = normalize_ticker(ticker)
    try:
        data = run_pipeline(ticker)
    except ValueError as exc:
        return render_template("index.html", error=str(exc))
    except ConnectionError as exc:
        return render_template(
            "index.html",
            error=f"Yahoo Finance is rate-limiting requests right now. Please wait 30-60 seconds and try again. ({exc})"
        )
    except Exception as exc:
        logger.exception("Pipeline error for %s", ticker)
        return render_template(
            "index.html",
            error=f"An unexpected error occurred while fetching data for '{ticker}'. "
                  f"Please try again in a moment. ({type(exc).__name__})"
        )

    # Prepare chart data (serializable for Jinja → JS)
    normalized = data["normalized"]
    periods = data["periods"]
    inc = normalized.get("income", {})
    cfs = normalized.get("cashflow", {})
    bal = normalized.get("balance", {})
    yoy = normalized.get("yoy", {})

    n = min(4, len(periods))
    chart_labels = list(reversed(periods[:n]))  # oldest → newest for chart

    def rev_list(s, count=n):
        """Reverse a series list to chronological order for Chart.js."""
        vals = series_to_list(s, count)
        return list(reversed(vals))

    chart_revenue = rev_list(inc.get("total_revenue"))
    chart_net_income = rev_list(inc.get("net_income"))
    chart_assets = rev_list(bal.get("total_assets"))
    chart_liabilities = rev_list(bal.get("total_liabilities"))

    # YoY for metric cards (most recent only)
    def yoy_val(key, idx=0):
        s = yoy.get(key)
        if s is None: return None
        try:
            v = float(s.iloc[idx])
            import math
            return None if math.isnan(v) else round(v, 1)
        except Exception:
            return None

    def latest_val(s, idx=0):
        if s is None: return None
        try:
            import math
            v = float(s.iloc[idx])
            return None if math.isnan(v) else round(v, 2)
        except Exception:
            return None

    def fmt_crore(v):
        if v is None: return "—"
        return f"₹ {v:,.2f} Cr"

    # Extract key line items for connected-statements display
    def extract_item(source_dict, key, idx=0):
        s = source_dict.get(key)
        return latest_val(s, idx)

    connected = {
        # Income Statement
        "is_revenue":       extract_item(inc, "total_revenue"),
        "is_cogs":          extract_item(inc, "cost_of_revenue"),
        "is_gross_profit":  extract_item(inc, "gross_profit"),
        "is_operating_income": extract_item(inc, "operating_income"),
        "is_ni":            extract_item(inc, "net_income"),
        "is_da":            extract_item(inc, "depreciation_income"),
        "is_interest":      extract_item(inc, "interest_expense"),
        "is_tax":           extract_item(inc, "tax_expense"),

        # Balance Sheet
        "bs_cash":          extract_item(bal, "cash"),
        "bs_ar":            extract_item(bal, "receivables"),
        "bs_inv":           extract_item(bal, "inventory_bs"),
        "bs_ppe":           extract_item(bal, "ppe_net"),
        "bs_total_assets":  extract_item(bal, "total_assets"),
        "bs_ap":            extract_item(bal, "payables"),
        "bs_debt":          extract_item(bal, "total_debt"),
        "bs_equity":        extract_item(bal, "total_equity"),
        "bs_retained":      extract_item(bal, "retained_earnings"),

        # Cash Flow
        "cfs_ni":           extract_item(cfs, "net_income_cfs"),
        "cfs_da":           extract_item(cfs, "depreciation_cfs"),
        "cfs_wc":           extract_item(cfs, "working_capital_change"),
        "cfs_ocf":          extract_item(cfs, "operating_cash_flow"),
        "cfs_capex":        extract_item(cfs, "capex"),
        "cfs_div":          extract_item(cfs, "dividends_paid"),
        "cfs_cash":         extract_item(cfs, "ending_cash"),
        "cfs_fcf":          None,  # derived below

        # Statement of Changes in Equity (derived)
        "scse_net_income":  extract_item(inc, "net_income"),
        "scse_div":         extract_item(cfs, "dividends_paid"),
        "scse_retained":    extract_item(bal, "retained_earnings"),
        "scse_equity":      extract_item(bal, "total_equity"),
    }

    # FCF = OCF + CapEx (capex is typically negative in yf)
    ocf = connected.get("cfs_ocf")
    capex = connected.get("cfs_capex")
    if ocf is not None and capex is not None:
        connected["cfs_fcf"] = round(ocf + capex, 2)

    def fc(v):
        """Format for connected statements display."""
        if v is None: return "—"
        return f"₹ {v:,.1f} Cr"

    return render_template(
        "dashboard.html",
        ticker=ticker,
        company_name=data["company_name"],
        info=data["info"],
        ratios=data["ratios"],
        checks=data["checks"],
        narrative=data["narrative"],
        periods=periods,
        as_of=data["as_of"],

        # Metric card values
        revenue=fmt_crore(latest_val(inc.get("total_revenue"))),
        revenue_yoy=yoy_val("total_revenue"),
        net_income=fmt_crore(latest_val(inc.get("net_income"))),
        net_income_yoy=yoy_val("net_income"),
        ocf=fmt_crore(latest_val(cfs.get("operating_cash_flow"))),
        ocf_yoy=yoy_val("operating_cash_flow"),

        # Chart data
        chart_labels=chart_labels,
        chart_revenue=chart_revenue,
        chart_net_income=chart_net_income,
        chart_assets=chart_assets,
        chart_liabilities=chart_liabilities,

        # Connected statements line items
        conn=connected,
        fc=fc,
    )


@app.route("/report/<ticker>")
def report(ticker: str):
    ticker = normalize_ticker(ticker)
    try:
        data = run_pipeline(ticker)
    except ValueError as exc:
        abort(404, description=str(exc))
    except Exception as exc:
        logger.exception("PDF pipeline error for %s", ticker)
        abort(500, description=str(exc))

    try:
        pdf_bytes = generate_pdf(
            ticker=ticker,
            normalized=data["normalized"],
            ratios=data["ratios"],
            checks=data["checks"],
            narrative=data["narrative"],
            company_info=data["info"],
            periods=data["periods"],
        )
    except Exception as exc:
        logger.exception("PDF generation error for %s", ticker)
        abort(500, description=f"PDF generation failed: {exc}")

    safe_ticker = ticker.replace(".NS", "").replace(".", "_")
    filename = f"Vitta_{safe_ticker}_Report_{date.today()}.pdf"

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message=str(e.description)), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message=str(e.description)), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "true").lower() == "true"
    logger.info("Starting Vitta on http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
