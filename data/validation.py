"""
data/validation.py
==================
Cross-statement linkage checks for the Vitta pipeline.

Each check returns a dict:
    {
        'name': str,
        'status': 'pass' | 'fail' | 'unable_to_verify',
        'message': str,
        'detail': str,   # optional extra context shown in UI
    }
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TOLERANCE_PCT = 0.05   # 5% tolerance for floating-point / rounding diffs
TOLERANCE_ABS = 100    # ₹100 Cr absolute tolerance (for very small companies)


def _val(s: Optional[pd.Series], period_idx: int = 0):
    """Safely extract a scalar value from a Series by position."""
    try:
        if s is None or s.empty:
            return None
        v = s.iloc[period_idx]
        return float(v) if not np.isnan(float(v)) else None
    except (IndexError, TypeError, ValueError):
        return None


def _close_enough(a: Optional[float], b: Optional[float]) -> bool:
    """Return True if a ≈ b within tolerance."""
    if a is None or b is None:
        return False
    if abs(a) < 1e-6 and abs(b) < 1e-6:
        return True
    diff = abs(a - b)
    if diff <= TOLERANCE_ABS:
        return True
    denom = max(abs(a), abs(b), 1.0)
    return (diff / denom) <= TOLERANCE_PCT


def check_cash_tieout(
    balance: dict,
    cashflow: dict,
) -> dict:
    """
    Ending cash balance on the CFS should equal Cash & Equivalents on the BS
    for the most-recent period.
    """
    name = "Cash Tie-Out"
    bs_cash = _val(balance.get("cash"))
    cfs_cash = _val(cashflow.get("ending_cash"))

    if bs_cash is None and cfs_cash is None:
        return {
            "name": name,
            "status": "unable_to_verify",
            "message": "Cash balance data unavailable in both statements.",
            "detail": "yfinance did not return a usable cash field.",
        }
    if bs_cash is None:
        return {
            "name": name,
            "status": "unable_to_verify",
            "message": "Balance sheet cash field unavailable.",
            "detail": f"CFS ending cash: ₹{cfs_cash:,.0f} Cr",
        }
    if cfs_cash is None:
        # Some tickers expose bs_cash but no ending_cash row on CFS
        return {
            "name": name,
            "status": "unable_to_verify",
            "message": "CFS ending cash field unavailable.",
            "detail": f"Balance sheet cash: ₹{bs_cash:,.0f} Cr",
        }

    ok = _close_enough(bs_cash, cfs_cash)
    diff = abs(bs_cash - cfs_cash)
    return {
        "name": name,
        "status": "pass" if ok else "fail",
        "message": (
            f"BS cash ₹{bs_cash:,.1f} Cr ≈ CFS ending cash ₹{cfs_cash:,.1f} Cr (diff: ₹{diff:,.1f} Cr)"
            if ok
            else f"Mismatch: BS cash ₹{bs_cash:,.1f} Cr vs CFS ending cash ₹{cfs_cash:,.1f} Cr (diff: ₹{diff:,.1f} Cr)"
        ),
        "detail": f"Difference: ₹{diff:,.1f} Cr ({diff/max(abs(bs_cash),1)*100:.1f}%)",
    }


def check_net_income_flow(
    income: dict,
    cashflow: dict,
) -> dict:
    """
    Net income on the IS should appear at the top of the operating section on the CFS.
    """
    name = "Net Income Flow (IS → CFS)"
    is_ni = _val(income.get("net_income"))
    cfs_ni = _val(cashflow.get("net_income_cfs"))

    if is_ni is None and cfs_ni is None:
        return {
            "name": name,
            "status": "unable_to_verify",
            "message": "Net income data unavailable in both statements.",
            "detail": "",
        }
    if is_ni is None:
        return {
            "name": name,
            "status": "unable_to_verify",
            "message": "Income statement net income unavailable.",
            "detail": f"CFS net income line: ₹{cfs_ni:,.0f} Cr",
        }
    if cfs_ni is None:
        return {
            "name": name,
            "status": "unable_to_verify",
            "message": "CFS net income line unavailable (yfinance may not separate it for this company).",
            "detail": f"IS net income: ₹{is_ni:,.0f} Cr",
        }

    ok = _close_enough(is_ni, cfs_ni)
    diff = abs(is_ni - cfs_ni)
    return {
        "name": name,
        "status": "pass" if ok else "fail",
        "message": (
            f"IS net income ₹{is_ni:,.1f} Cr ≈ CFS operating start ₹{cfs_ni:,.1f} Cr"
            if ok
            else f"Mismatch: IS net income ₹{is_ni:,.1f} Cr vs CFS start ₹{cfs_ni:,.1f} Cr (diff: ₹{diff:,.1f} Cr)"
        ),
        "detail": f"Difference: ₹{diff:,.1f} Cr",
    }


def check_earnings_quality(
    income: dict,
    cashflow: dict,
) -> dict:
    """
    Red-flag check: Net Income positive but Operating Cash Flow negative.
    This is the major earnings-quality warning (possible accrual manipulation).
    """
    name = "Earnings Quality (NI vs OCF)"
    ni = _val(income.get("net_income"))
    ocf = _val(cashflow.get("operating_cash_flow"))

    if ni is None or ocf is None:
        return {
            "name": name,
            "status": "unable_to_verify",
            "message": "Cannot assess earnings quality — data unavailable.",
            "detail": "",
        }

    if ni > 0 and ocf < 0:
        return {
            "name": name,
            "status": "fail",
            "message": f"⚠ Net income ₹{ni:,.1f} Cr is POSITIVE but OCF ₹{ocf:,.1f} Cr is NEGATIVE — potential earnings quality concern.",
            "detail": "This pattern can indicate aggressive revenue recognition or large non-cash credits inflating reported profit.",
        }

    return {
        "name": name,
        "status": "pass",
        "message": f"Net income ₹{ni:,.1f} Cr and OCF ₹{ocf:,.1f} Cr are directionally consistent.",
        "detail": "",
    }


def run_all_checks(normalized: dict) -> list[dict]:
    """
    Run all validation checks and return a list of result dicts.
    `normalized` is the output of transform.normalize_financials().
    """
    income = normalized.get("income", {})
    balance = normalized.get("balance", {})
    cashflow = normalized.get("cashflow", {})

    checks = [
        check_cash_tieout(balance, cashflow),
        check_net_income_flow(income, cashflow),
        check_earnings_quality(income, cashflow),
    ]
    return checks
