"""
data/transform.py
=================
Currency normalization and YoY change calculations for the Vitta pipeline.

yfinance returns Indian-company figures in raw INR (not thousands, not lakhs).
1 Crore = 10,000,000 = 1e7.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CRORE = 1e7  # 1 Crore = 10,000,000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_get(df: pd.DataFrame, *candidate_labels: str) -> Optional[pd.Series]:
    """
    Look up a row in a DataFrame by trying a list of candidate index labels.
    Returns the first match as a Series, or None if nothing matches.
    Case-insensitive, strips whitespace.
    """
    if df is None or df.empty:
        return None
    norm_index = {str(k).strip().lower(): k for k in df.index}
    for label in candidate_labels:
        key = label.strip().lower()
        if key in norm_index:
            return df.loc[norm_index[key]]
    return None


def _to_crore(series: Optional[pd.Series]) -> Optional[pd.Series]:
    """Convert a raw-INR Series to ₹ Crore (divide by 1e7). Returns None if input is None."""
    if series is None:
        return None
    return series / CRORE


def _yoy_pct(series: Optional[pd.Series]) -> Optional[pd.Series]:
    """
    Compute year-over-year percentage change.
    Series is expected to have columns sorted most-recent-first (as fetcher delivers).
    We reverse to chronological order, compute pct_change, then reverse back.
    """
    if series is None or len(series) < 2:
        return None
    s = series[::-1].astype(float)          # oldest → newest
    pct = s.pct_change() * 100              # NaN for first element
    return pct[::-1]                        # back to newest-first


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

INCOME_FIELDS = {
    # canonical_name: [candidate yfinance labels, ordered by preference]
    "total_revenue": [
        "Total Revenue", "Revenue", "Net Revenue", "TotalRevenue",
    ],
    "gross_profit": [
        "Gross Profit", "GrossProfit",
    ],
    "operating_income": [
        "Operating Income", "EBIT", "OperatingIncome",
    ],
    "ebitda": [
        "EBITDA", "Ebitda",
    ],
    "net_income": [
        "Net Income", "NetIncome", "Net Income Common Stockholders",
        "Net Income From Continuing And Discontinued Operation",
        "Net Income From Continuing Operation Net Minority Interest",
    ],
    "interest_expense": [
        "Interest Expense", "InterestExpense",
    ],
    "tax_expense": [
        "Tax Provision", "Income Tax Expense/Benefit", "IncomeTaxExpense",
    ],
    "depreciation_income": [
        "Reconciled Depreciation", "Depreciation", "DepreciationAndAmortization",
    ],
    "cost_of_revenue": [
        "Cost Of Revenue", "CostOfRevenue", "Cost Of Goods Sold",
    ],
    "inventory": [
        "Inventory", "Inventories",
    ],
}

BALANCE_FIELDS = {
    "total_assets": [
        "Total Assets", "TotalAssets",
    ],
    "total_equity": [
        "Stockholders Equity", "Total Stockholders Equity",
        "Common Stock Equity", "StockholdersEquity",
        "Total Equity Gross Minority Interest",
    ],
    "total_debt": [
        "Total Debt", "Long Term Debt And Capital Lease Obligation",
        "Long Term Debt", "TotalDebt",
    ],
    "long_term_debt": [
        "Long Term Debt", "LongTermDebt",
        "Long Term Debt And Capital Lease Obligation",
    ],
    "cash": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash Equivalents", "CashAndCashEquivalents",
    ],
    "receivables": [
        "Net Receivables", "Receivables", "Accounts Receivable",
        "Current Notes Receivable",
    ],
    "payables": [
        "Accounts Payable", "AccountsPayable", "Payables",
    ],
    "inventory_bs": [
        "Inventory", "Inventories",
    ],
    "ppe_net": [
        "Net PPE", "Property Plant Equipment Net", "NetPPE",
        "Gross PPE",
    ],
    "retained_earnings": [
        "Retained Earnings", "RetainedEarnings",
    ],
    "total_liabilities": [
        "Total Liabilities Net Minority Interest", "Total Liabilities",
        "TotalLiabilitiesNetMinorityInterest",
    ],
    "current_assets": [
        "Current Assets", "Total Current Assets", "CurrentAssets",
    ],
    "current_liabilities": [
        "Current Liabilities", "Total Current Liabilities", "CurrentLiabilities",
    ],
}

CASHFLOW_FIELDS = {
    "operating_cash_flow": [
        "Operating Cash Flow", "Cash From Operations",
        "Net Cash Provided By Operating Activities",
        "OperatingCashFlow",
    ],
    "capex": [
        "Capital Expenditure", "CapEx", "Purchase Of PPE",
        "Capital Expenditures",
    ],
    "net_income_cfs": [
        "Net Income From Continuing Operations", "Net Income",
        "NetIncomeFromContinuingOperations",
    ],
    "depreciation_cfs": [
        "Depreciation And Amortization", "DepreciationAndAmortization",
        "Reconciled Depreciation", "Depreciation",
        "Depreciation Amortization Depletion",
    ],
    "working_capital_change": [
        "Change In Working Capital", "Changes In Working Capital",
        "ChangeInWorkingCapital",
    ],
    "dividends_paid": [
        "Common Stock Dividend Paid", "Dividends Paid",
        "Payment Of Dividends", "CashDividendsPaid",
    ],
    "ending_cash": [
        "End Cash Position", "Cash And Cash Equivalents At End Of Period",
        "EndCashPosition", "Changes In Cash",
    ],
    "investing_cash_flow": [
        "Investing Cash Flow", "Cash From Investing",
        "Net Cash Provided By Investing Activities",
        "InvestingCashFlow",
    ],
    "financing_cash_flow": [
        "Financing Cash Flow", "Cash From Financing",
        "Net Cash Provided By Financing Activities",
        "FinancingCashFlow",
    ],
}


def _extract_field(df: pd.DataFrame, candidates: list[str]) -> Optional[pd.Series]:
    return _safe_get(df, *candidates)


def normalize_financials(raw: dict) -> dict:
    """
    Given raw dict from fetcher.get_all_data(), return a normalized dict:
    {
        'income': { field_name: Series(₹ Crore, newest-first), ... },
        'balance': { ... },
        'cashflow': { ... },
        'yoy': { field_name: Series(% change, newest-first), ... },
        'periods': list of period label strings (newest-first),
    }
    Missing fields are stored as None — consumers must handle None.
    """
    inc = raw.get("income", pd.DataFrame())
    bal = raw.get("balance", pd.DataFrame())
    cfs = raw.get("cashflow", pd.DataFrame())

    result_income = {}
    for canon, candidates in INCOME_FIELDS.items():
        s = _extract_field(inc, candidates)
        result_income[canon] = _to_crore(s)

    result_balance = {}
    for canon, candidates in BALANCE_FIELDS.items():
        s = _extract_field(bal, candidates)
        result_balance[canon] = _to_crore(s)

    result_cashflow = {}
    for canon, candidates in CASHFLOW_FIELDS.items():
        s = _extract_field(cfs, candidates)
        result_cashflow[canon] = _to_crore(s)

    # Derive periods from income statement (most complete)
    periods = []
    if not inc.empty:
        periods = [str(c)[:10] for c in inc.columns]  # YYYY-MM-DD
    elif not bal.empty:
        periods = [str(c)[:10] for c in bal.columns]

    # YoY changes for key metrics
    yoy = {}
    for metric in ["total_revenue", "net_income"]:
        yoy[metric] = _yoy_pct(result_income.get(metric))
    yoy["operating_cash_flow"] = _yoy_pct(result_cashflow.get("operating_cash_flow"))

    return {
        "income": result_income,
        "balance": result_balance,
        "cashflow": result_cashflow,
        "yoy": yoy,
        "periods": periods,
    }


def fmt_crore(value, decimals: int = 2) -> str:
    """Format a single float as '₹ X,XXX.XX Cr' string. Returns '—' for None/NaN."""
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return "—"
        return f"₹ {value:,.{decimals}f} Cr"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(value, decimals: int = 1) -> str:
    """Format a percentage value. Returns '—' for None/NaN."""
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return "—"
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def series_to_list(s: Optional[pd.Series], n: int = 4) -> list:
    """Convert a Series to a list of at most n float values (None for NaN)."""
    if s is None:
        return [None] * n
    vals = []
    for v in s.iloc[:n]:
        try:
            fv = float(v)
            vals.append(None if np.isnan(fv) else fv)
        except (TypeError, ValueError):
            vals.append(None)
    # Pad with None if fewer than n periods
    while len(vals) < n:
        vals.append(None)
    return vals
