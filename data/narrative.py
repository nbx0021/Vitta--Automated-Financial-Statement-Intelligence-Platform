"""
data/narrative.py
=================
Rule-based (NOT LLM) narrative summary generation for the Vitta pipeline.
Produces a short analyst-style paragraph from computed numbers.
"""
from __future__ import annotations

from typing import Optional


def _safe(v: Optional[float], default: str = "N/A") -> str:
    if v is None:
        return default
    return f"{v:,.1f}"


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "unavailable"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def build_narrative(
    normalized: dict,
    ratios: dict,
    checks: list,
    company_name: str,
    periods: list,
) -> str:
    """
    Generate a deterministic, template-driven narrative paragraph.
    Returns an HTML-safe string (no tags, plain text for the dashboard).
    """
    inc = normalized.get("income", {})
    cfs = normalized.get("cashflow", {})
    bal = normalized.get("balance", {})
    yoy = normalized.get("yoy", {})

    # --- helpers to get most-recent scalar ---
    def v(d: dict, key: str) -> Optional[float]:
        s = d.get(key)
        if s is None or s.empty:
            return None
        try:
            val = float(s.iloc[0])
            import math
            return None if math.isnan(val) else val
        except Exception:
            return None

    ni = v(inc, "net_income")
    rev = v(inc, "total_revenue")
    ocf = v(cfs, "operating_cash_flow")
    debt = v(bal, "total_debt")
    equity = v(bal, "total_equity")
    rev_yoy = v(yoy, "total_revenue")

    # Find ratio values
    def find_ratio(name: str) -> Optional[float]:
        for group in [ratios.get("sector_ratios", []), ratios.get("universal_ratios", [])]:
            for r in group:
                if r["name"] == name:
                    return r.get("value")
        return None

    roe = find_ratio("return_on_equity")
    roic = find_ratio("roic")
    d_ebitda = find_ratio("debt_to_ebitda")

    period_str = periods[0] if periods else "most recent period"

    parts = []

    # --- Profitability / Earnings Quality ---
    if ni is not None and ocf is not None:
        if ni > 0 and ocf < 0:
            parts.append(
                f"{company_name} reported net income of ₹{_safe(ni)} Cr for {period_str}, "
                f"but generated NEGATIVE operating cash flow of ₹{_safe(ocf)} Cr — "
                f"a significant red flag suggesting earnings may be propped up by accounting accruals "
                f"rather than real cash generation."
            )
        elif ni > 0 and ocf > 0:
            ratio_str = f"{ocf/ni:.1f}x" if ni != 0 else "N/A"
            parts.append(
                f"{company_name} reported net income of ₹{_safe(ni)} Cr with operating cash flow of "
                f"₹{_safe(ocf)} Cr (OCF-to-NI ratio: {ratio_str}), indicating good earnings quality — "
                f"reported profits are largely backed by cash generation."
            )
        elif ni < 0:
            parts.append(
                f"{company_name} reported a net loss of ₹{_safe(abs(ni) if ni else None)} Cr for {period_str}. "
                f"Operating cash flow stood at ₹{_safe(ocf)} Cr."
            )
    elif ni is not None:
        parts.append(
            f"{company_name} reported net income of ₹{_safe(ni)} Cr for {period_str}."
        )
    else:
        parts.append(f"Financial data for {company_name} is partially unavailable.")

    # Revenue growth commentary
    if rev_yoy is not None:
        direction = "grew" if rev_yoy >= 0 else "declined"
        parts.append(
            f"Revenue {direction} {_pct(rev_yoy)} year-over-year."
        )

    # --- Solvency ---
    if d_ebitda is not None:
        if d_ebitda < 1.0:
            parts.append(
                f"On the solvency front, Debt/EBITDA of {d_ebitda:.1f}x is comfortable, "
                f"suggesting manageable leverage relative to earnings power."
            )
        elif d_ebitda < 3.0:
            parts.append(
                f"Debt/EBITDA of {d_ebitda:.1f}x reflects moderate leverage — "
                f"serviceable but worth monitoring in a rising-rate environment."
            )
        elif d_ebitda < 5.0:
            parts.append(
                f"Debt/EBITDA of {d_ebitda:.1f}x is elevated; debt servicing is a meaningful cost burden "
                f"and warrants close attention to cash flow sustainability."
            )
        else:
            parts.append(
                f"Debt/EBITDA of {d_ebitda:.1f}x is HIGH — the company carries substantial financial risk "
                f"relative to its earnings before interest, taxes, depreciation, and amortization."
            )
    else:
        parts.append("Solvency metrics (Debt/EBITDA) could not be calculated with available data.")

    # --- Efficiency ---
    if roe is not None and roic is not None:
        if roe > 15 and roic > 12:
            parts.append(
                f"Efficiency metrics are strong: ROE of {_pct(roe)} and ROIC of {_pct(roic)} indicate "
                f"the company is generating solid returns on both shareholder and invested capital."
            )
        elif roe > 0 and roic > 0:
            parts.append(
                f"ROE stands at {_pct(roe)} and ROIC at {_pct(roic)}, reflecting positive but "
                f"modest capital efficiency — management would need to improve returns to create "
                f"meaningful economic value over its cost of capital."
            )
        else:
            parts.append(
                f"ROE of {_pct(roe)} and ROIC of {_pct(roic)} indicate the company is currently "
                f"destroying economic value — returns on capital are below typical equity cost thresholds."
            )
    elif roe is not None:
        parts.append(f"Return on Equity stands at {_pct(roe)}.")

    parts.append(
        "Note: This is a rule-based analytical summary generated from publicly available financial data. "
        "It is not investment advice."
    )

    return " ".join(parts)
