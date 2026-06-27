"""
data/sectors.py
===============
Sector classification and sector-appropriate ratio computation.

Design: completely config-driven.  To add a new sector, add a key to
SECTOR_CONFIG — no new code needed.

Sector strings come from yfinance company info (.sector field).
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sector mapping config
# ---------------------------------------------------------------------------
# yfinance sector strings (case-insensitive prefix match) → internal bucket
SECTOR_MAPPING = [
    # (substring_to_match_in_yf_sector, internal_bucket)
    ("technology", "tech"),
    ("software", "tech"),
    ("information technology", "tech"),
    ("communication services", "tech"),
    ("consumer discretionary", "manufacturing"),
    ("consumer staples", "manufacturing"),
    ("retail", "manufacturing"),
    ("industrials", "manufacturing"),
    ("materials", "manufacturing"),
    ("health care", "manufacturing"),
    ("healthcare", "manufacturing"),
    ("pharmaceuticals", "manufacturing"),
    ("energy", "energy"),
    ("utilities", "energy"),
    ("real estate", "energy"),
    ("telecom", "energy"),
    ("telecommunication", "energy"),
    ("financials", "banking"),
    ("financial services", "banking"),
    ("banking", "banking"),
    ("insurance", "banking"),
    ("nbfc", "banking"),
]

# Config dict: bucket → list of ratio names to compute for that sector
SECTOR_CONFIG = {
    "tech": {
        "label": "Technology / IT Services",
        "ratios": ["gross_margin", "revenue_growth"],
    },
    "manufacturing": {
        "label": "Manufacturing / FMCG / Retail",
        "ratios": ["inventory_turnover", "gross_margin", "return_on_assets"],
    },
    "energy": {
        "label": "Energy / Capital-Heavy / Telecom",
        "ratios": ["debt_to_equity", "capex_pct_revenue", "ev_ebitda"],
    },
    "banking": {
        "label": "Banking / NBFC / Financial Services",
        "ratios": ["net_interest_margin", "return_on_equity", "leverage_ratio"],
    },
    "default": {
        "label": "Diversified / Other",
        "ratios": ["gross_margin", "return_on_assets"],
    },
}

# Ratios always computed regardless of sector
UNIVERSAL_RATIOS = ["return_on_equity", "roic", "debt_to_ebitda"]


# ---------------------------------------------------------------------------
# Sector classification
# ---------------------------------------------------------------------------

def classify_sector(yf_sector: Optional[str]) -> str:
    """Map a yfinance sector string to an internal bucket name."""
    if not yf_sector:
        return "default"
    s = yf_sector.lower()
    for substring, bucket in SECTOR_MAPPING:
        if substring in s:
            return bucket
    return "default"


# ---------------------------------------------------------------------------
# Individual ratio calculators
# ---------------------------------------------------------------------------

def _v(s: Optional[pd.Series], idx: int = 0) -> Optional[float]:
    """Safely get float value from a Series at position idx."""
    try:
        if s is None or s.empty:
            return None
        v = float(s.iloc[idx])
        return None if math.isnan(v) else v
    except (IndexError, TypeError, ValueError):
        return None


def _avg(s: Optional[pd.Series], idx_a: int = 0, idx_b: int = 1) -> Optional[float]:
    """Average of two positions in a Series (used for beginning/ending averages)."""
    a, b = _v(s, idx_a), _v(s, idx_b)
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2


def calc_gross_margin(income: dict) -> Optional[float]:
    rev = _v(income.get("total_revenue"))
    gp = _v(income.get("gross_profit"))
    if rev and rev != 0 and gp is not None:
        return (gp / rev) * 100
    return None


def calc_revenue_growth(yoy: dict) -> Optional[float]:
    s = yoy.get("total_revenue")
    return _v(s, 0)   # most-recent YoY %


def calc_inventory_turnover(income: dict, balance: dict) -> Optional[float]:
    cogs = _v(income.get("cost_of_revenue"))
    inv = _avg(balance.get("inventory_bs"), 0, 1)
    if cogs and inv and inv != 0:
        return cogs / inv
    return None


def calc_return_on_assets(income: dict, balance: dict) -> Optional[float]:
    ni = _v(income.get("net_income"))
    assets = _avg(balance.get("total_assets"), 0, 1)
    if ni is not None and assets and assets != 0:
        return (ni / assets) * 100
    return None


def calc_debt_to_equity(balance: dict) -> Optional[float]:
    debt = _v(balance.get("total_debt"))
    equity = _v(balance.get("total_equity"))
    if debt is not None and equity and equity != 0:
        return debt / equity
    return None


def calc_capex_pct_revenue(income: dict, cashflow: dict) -> Optional[float]:
    capex = _v(cashflow.get("capex"))
    rev = _v(income.get("total_revenue"))
    if capex is not None and rev and rev != 0:
        return (abs(capex) / rev) * 100
    return None


def calc_ev_ebitda(info: dict, income: dict) -> Optional[float]:
    ev = info.get("enterpriseValue")
    ebitda_raw = info.get("ebitda")
    if ev and ebitda_raw:
        # info values are in raw INR — convert both the same way
        ev_crore = ev / 1e7
        ebitda_crore = ebitda_raw / 1e7
        if ebitda_crore != 0:
            return ev_crore / ebitda_crore
    # fallback: compute from IS
    ebitda = _v(income.get("ebitda"))
    if ebitda and ebitda != 0:
        # We don't have EV from IS alone; return None
        pass
    return None


def calc_net_interest_margin(income: dict, balance: dict) -> Optional[float]:
    """NIM = (Interest Income - Interest Expense) / Earning Assets. Rough proxy for banks."""
    # yfinance rarely gives interest income separately; use total revenue as proxy for banking
    rev = _v(income.get("total_revenue"))
    int_exp = _v(income.get("interest_expense"))
    assets = _avg(balance.get("total_assets"), 0, 1)
    if rev is not None and int_exp is not None and assets and assets != 0:
        net_interest = rev - abs(int_exp)
        return (net_interest / assets) * 100
    return None


def calc_return_on_equity(income: dict, balance: dict) -> Optional[float]:
    ni = _v(income.get("net_income"))
    equity = _avg(balance.get("total_equity"), 0, 1)
    if ni is not None and equity and equity != 0:
        return (ni / equity) * 100
    return None


def calc_leverage_ratio(balance: dict) -> Optional[float]:
    """Simple leverage: Total Assets / Total Equity."""
    assets = _v(balance.get("total_assets"))
    equity = _v(balance.get("total_equity"))
    if assets is not None and equity and equity != 0:
        return assets / equity
    return None


def calc_roic(income: dict, balance: dict) -> Optional[float]:
    """ROIC = NOPAT / Invested Capital (best-effort)."""
    ebit = _v(income.get("operating_income"))
    tax = _v(income.get("tax_expense"))
    ni = _v(income.get("net_income"))
    rev = _v(income.get("total_revenue"))

    # Estimate effective tax rate
    if ebit and tax is not None and ebit != 0:
        tax_rate = abs(tax) / abs(ebit)
        tax_rate = min(max(tax_rate, 0), 0.5)  # clamp 0-50%
        nopat = ebit * (1 - tax_rate)
    elif ni is not None:
        nopat = ni
    else:
        return None

    debt = _v(balance.get("total_debt"))
    equity = _v(balance.get("total_equity"))
    invested_capital = (debt or 0) + (equity or 0)
    if invested_capital and invested_capital != 0:
        return (nopat / invested_capital) * 100
    return None


def calc_debt_to_ebitda(income: dict, balance: dict) -> Optional[float]:
    debt = _v(balance.get("total_debt"))
    ebitda = _v(income.get("ebitda"))
    if ebitda is None:
        # Construct: operating income + D&A
        oi = _v(income.get("operating_income"))
        da = _v(income.get("depreciation_income"))
        if oi is not None and da is not None:
            ebitda = oi + abs(da)
        elif oi is not None:
            ebitda = oi
    if debt is not None and ebitda and ebitda != 0:
        return debt / ebitda
    return None


# ---------------------------------------------------------------------------
# Ratio dispatcher
# ---------------------------------------------------------------------------

RATIO_CALCULATORS = {
    "gross_margin":         lambda i, b, c, cf, y, inf: calc_gross_margin(i),
    "revenue_growth":       lambda i, b, c, cf, y, inf: calc_revenue_growth(y),
    "inventory_turnover":   lambda i, b, c, cf, y, inf: calc_inventory_turnover(i, b),
    "return_on_assets":     lambda i, b, c, cf, y, inf: calc_return_on_assets(i, b),
    "debt_to_equity":       lambda i, b, c, cf, y, inf: calc_debt_to_equity(b),
    "capex_pct_revenue":    lambda i, b, c, cf, y, inf: calc_capex_pct_revenue(i, cf),
    "ev_ebitda":            lambda i, b, c, cf, y, inf: calc_ev_ebitda(inf, i),
    "net_interest_margin":  lambda i, b, c, cf, y, inf: calc_net_interest_margin(i, b),
    "return_on_equity":     lambda i, b, c, cf, y, inf: calc_return_on_equity(i, b),
    "leverage_ratio":       lambda i, b, c, cf, y, inf: calc_leverage_ratio(b),
    "roic":                 lambda i, b, c, cf, y, inf: calc_roic(i, b),
    "debt_to_ebitda":       lambda i, b, c, cf, y, inf: calc_debt_to_ebitda(i, b),
}

RATIO_META = {
    "gross_margin":         {"label": "Gross Margin",              "unit": "%",  "fmt": "{:.1f}%"},
    "revenue_growth":       {"label": "Revenue Growth (YoY)",      "unit": "%",  "fmt": "{:+.1f}%"},
    "inventory_turnover":   {"label": "Inventory Turnover",        "unit": "x",  "fmt": "{:.2f}x"},
    "return_on_assets":     {"label": "Return on Assets",          "unit": "%",  "fmt": "{:.1f}%"},
    "debt_to_equity":       {"label": "Debt-to-Equity",            "unit": "x",  "fmt": "{:.2f}x"},
    "capex_pct_revenue":    {"label": "CapEx % Revenue",           "unit": "%",  "fmt": "{:.1f}%"},
    "ev_ebitda":            {"label": "EV / EBITDA",               "unit": "x",  "fmt": "{:.1f}x"},
    "net_interest_margin":  {"label": "Net Interest Margin",       "unit": "%",  "fmt": "{:.2f}%"},
    "return_on_equity":     {"label": "Return on Equity",          "unit": "%",  "fmt": "{:.1f}%"},
    "leverage_ratio":       {"label": "Leverage Ratio (A/E)",      "unit": "x",  "fmt": "{:.1f}x"},
    "roic":                 {"label": "Return on Invested Capital","unit": "%",  "fmt": "{:.1f}%"},
    "debt_to_ebitda":       {"label": "Debt / EBITDA",             "unit": "x",  "fmt": "{:.1f}x"},
}


def compute_ratios(normalized: dict, info: dict) -> dict:
    """
    Compute all relevant ratios for the company's sector plus universal ratios.
    Returns:
        {
            'sector_bucket': str,
            'sector_label': str,
            'sector_ratios': [{'name': str, 'label': str, 'value': float|None, 'formatted': str}, ...],
            'universal_ratios': [...],
        }
    """
    yf_sector = info.get("sector", "")
    bucket = classify_sector(yf_sector)
    config = SECTOR_CONFIG.get(bucket, SECTOR_CONFIG["default"])

    inc = normalized.get("income", {})
    bal = normalized.get("balance", {})
    cfs = normalized.get("cashflow", {})
    yoy = normalized.get("yoy", {})

    def _compute(ratio_name: str) -> dict:
        calc = RATIO_CALCULATORS.get(ratio_name)
        meta = RATIO_META.get(ratio_name, {"label": ratio_name, "unit": "", "fmt": "{}"})
        value = None
        if calc:
            try:
                value = calc(inc, bal, cfs, cfs, yoy, info)
            except Exception as e:
                logger.warning("Ratio %s failed: %s", ratio_name, e)
        formatted = "—"
        if value is not None:
            try:
                formatted = meta["fmt"].format(value)
            except Exception:
                formatted = f"{value:.2f}"
        return {
            "name": ratio_name,
            "label": meta["label"],
            "unit": meta["unit"],
            "value": value,
            "formatted": formatted,
        }

    sector_ratios = [_compute(r) for r in config["ratios"]]
    universal_ratios = [_compute(r) for r in UNIVERSAL_RATIOS]

    # De-duplicate: remove universal ratios already in sector ratios
    sector_names = {r["name"] for r in sector_ratios}
    universal_ratios = [r for r in universal_ratios if r["name"] not in sector_names]

    return {
        "sector_bucket": bucket,
        "sector_label": config["label"],
        "sector_ratios": sector_ratios,
        "universal_ratios": universal_ratios,
    }
