"""
reports/generator.py
====================
PDF report generation for the Vitta platform using ReportLab + matplotlib.

Flow:
  1. matplotlib renders a trend chart → BytesIO PNG
  2. ReportLab assembles the PDF document with the chart embedded

No external services, no API keys.
"""
from __future__ import annotations

import io
import logging
import math
from datetime import date

import matplotlib
matplotlib.use("Agg")  # non-interactive backend, must be before pyplot import
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Color palette (matches the CSS design system)
# ---------------------------------------------------------------------------
BRAND_DARK = colors.HexColor("#0F172A")
BRAND_ACCENT = colors.HexColor("#6366F1")
BRAND_ACCENT2 = colors.HexColor("#06B6D4")
GREEN = colors.HexColor("#10B981")
RED = colors.HexColor("#EF4444")
AMBER = colors.HexColor("#F59E0B")
LIGHT_GRAY = colors.HexColor("#F8FAFC")
MID_GRAY = colors.HexColor("#CBD5E1")
TEXT_DARK = colors.HexColor("#1E293B")
TEXT_MUTED = colors.HexColor("#64748B")


# ---------------------------------------------------------------------------
# matplotlib chart rendering
# ---------------------------------------------------------------------------

def _render_trend_chart(normalized: dict, periods: list, company_name: str) -> io.BytesIO:
    """Render Revenue vs Net Income trend chart as PNG in a BytesIO buffer."""
    inc = normalized.get("income", {})

    rev_series = inc.get("total_revenue")
    ni_series = inc.get("net_income")

    # Build lists (chronological: oldest first for the chart)
    def _to_list(s, n=4):
        if s is None:
            return [None] * n
        vals = []
        for v in reversed(list(s.iloc[:n])):
            try:
                fv = float(v)
                vals.append(None if math.isnan(fv) else fv)
            except Exception:
                vals.append(None)
        return vals

    n = min(4, len(periods))
    labels = list(reversed(periods[:n]))  # oldest first
    rev_vals = _to_list(rev_series, n)
    ni_vals = _to_list(ni_series, n)

    fig, ax = plt.subplots(figsize=(7.5, 3.5))
    fig.patch.set_facecolor("#0F172A")
    ax.set_facecolor("#1E293B")

    x = range(len(labels))
    width = 0.35

    # Filter None values for plotting
    rev_plot = [v if v is not None else 0 for v in rev_vals]
    ni_plot = [v if v is not None else 0 for v in ni_vals]

    bars1 = ax.bar([i - width/2 for i in x], rev_plot, width,
                   label="Revenue", color="#6366F1", alpha=0.85)
    bars2 = ax.bar([i + width/2 for i in x], ni_plot, width,
                   label="Net Income", color="#06B6D4", alpha=0.85)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, color="#CBD5E1", fontsize=8)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda val, _: f"Rs.{val/1:.0f} Cr" if abs(val) < 1e6 else f"Rs.{val/1e3:.0f}K Cr"
    ))
    ax.tick_params(colors="#CBD5E1", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#475569")
    ax.spines["bottom"].set_color("#475569")
    ax.yaxis.label.set_color("#CBD5E1")
    ax.set_ylabel("Rs. Crore", color="#CBD5E1", fontsize=9)
    ax.set_title(f"{company_name} — Revenue vs Net Income", color="#F1F5F9", fontsize=10, pad=10)
    legend = ax.legend(facecolor="#1E293B", edgecolor="#475569", labelcolor="#CBD5E1", fontsize=8)
    ax.grid(axis="y", color="#334155", linewidth=0.5, linestyle="--", alpha=0.5)

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# PDF document assembly
# ---------------------------------------------------------------------------

def _get_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "VittaTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=BRAND_ACCENT,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "VittaSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=TEXT_MUTED,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "VittaH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=BRAND_ACCENT,
        spaceBefore=14,
        spaceAfter=6,
        borderPad=0,
    ))
    styles.add(ParagraphStyle(
        "VittaBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        textColor=TEXT_DARK,
        leading=14,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        "VittaCallout",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=TEXT_DARK,
        leading=13,
        backColor=colors.HexColor("#EEF2FF"),
        borderColor=BRAND_ACCENT,
        borderWidth=1,
        borderPad=8,
        borderRadius=4,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "VittaFooter",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        textColor=TEXT_MUTED,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "VittaTableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        "VittaTableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        textColor=TEXT_DARK,
    ))
    return styles


def _delta_str(value) -> str:
    """Format a YoY value as a +/- string."""
    try:
        if value is None or math.isnan(float(value)):
            return "—"
        f = float(value)
        return f"+{f:.1f}%" if f >= 0 else f"{f:.1f}%"
    except Exception:
        return "—"


def generate_pdf(
    ticker: str,
    normalized: dict,
    ratios: dict,
    checks: list,
    narrative: str,
    company_info: dict,
    periods: list,
    piotroski: dict = None,
    altman: dict = None,
    dcf: dict = None,
) -> bytes:
    """
    Assemble and return the full PDF as bytes.
    """
    styles = _get_styles()

    company_name = (
        company_info.get("longName")
        or company_info.get("shortName")
        or ticker.upper()
    )
    sector_label = ratios.get("sector_label", "—")
    today = date.today().strftime("%d %B %Y")

    buf = io.BytesIO()

    # Custom page template with margins
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2.5*cm,
        bottomMargin=2.5*cm,
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="main",
    )

    def _header_footer(canvas, doc):
        canvas.saveState()
        # Header bar
        canvas.setFillColor(BRAND_DARK)
        canvas.rect(0, A4[1] - 1.5*cm, A4[0], 1.5*cm, fill=1, stroke=0)
        canvas.setFillColor(BRAND_ACCENT)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(2*cm, A4[1] - 1.0*cm, "VITTA")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(2*cm + 60, A4[1] - 1.0*cm,
                          "Automated Financial Statement Intelligence")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 2*cm, A4[1] - 1.0*cm, today)

        # Footer
        canvas.setFillColor(TEXT_MUTED)
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.drawCentredString(A4[0]/2, 1.2*cm,
            "Data source: Yahoo Finance (yfinance). For informational purposes only — not investment advice.")
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(A4[0] - 2*cm, 1.2*cm, f"Page {doc.page}")
        canvas.restoreState()

    template = PageTemplate(id="main", frames=[frame], onPage=_header_footer)
    doc.addPageTemplates([template])

    story = []

    # --- Cover block ---
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(company_name, styles["VittaTitle"]))
    story.append(Paragraph(
        f"<b>{ticker.upper()}</b> &nbsp;|&nbsp; {sector_label} &nbsp;|&nbsp; Report Date: {today}",
        styles["VittaSubtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT, spaceAfter=12))

    # --- Executive summary ---
    story.append(Paragraph("Executive Summary", styles["VittaH2"]))
    story.append(Paragraph(narrative, styles["VittaCallout"]))

    # --- Linkage validation ---
    story.append(Paragraph("Cross-Statement Linkage Checks", styles["VittaH2"]))
    check_rows = [["Check", "Status", "Details"]]
    for chk in checks:
        status = chk.get("status", "—")
        color_map = {"pass": "✓", "fail": "✗", "unable_to_verify": "?"}
        icon = color_map.get(status, "—")
        check_rows.append([
            Paragraph(chk.get("name", "—"), styles["VittaTableCell"]),
            Paragraph(f"{icon} {status.replace('_', ' ').title()}", styles["VittaTableCell"]),
            Paragraph(chk.get("message", "—"), styles["VittaTableCell"]),
        ])

    chk_table = Table(check_rows, colWidths=[4.5*cm, 3.5*cm, 9*cm])
    chk_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_GRAY, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(chk_table)
    story.append(Spacer(1, 0.4*cm))

    # --- Key metrics table ---
    story.append(Paragraph("Key Financial Metrics", styles["VittaH2"]))

    inc = normalized.get("income", {})
    cfs = normalized.get("cashflow", {})
    yoy = normalized.get("yoy", {})

    def _cr(s, idx=0):
        try:
            if s is None: return "—"
            v = float(s.iloc[idx])
            if math.isnan(v): return "—"
            return f"Rs. {v:,.1f} Cr"
        except Exception:
            return "—"

    def _yoy(s, idx=0):
        try:
            if s is None: return "—"
            v = float(s.iloc[idx])
            if math.isnan(v): return "—"
            return ("+" if v >= 0 else "") + f"{v:.1f}%"
        except Exception:
            return "—"

    period0 = periods[0] if periods else "Latest"

    metric_rows = [
        [Paragraph("Metric", styles["VittaTableHeader"]),
         Paragraph("Latest", styles["VittaTableHeader"]),
         Paragraph("YoY Change", styles["VittaTableHeader"])],
        ["Revenue",
         _cr(inc.get("total_revenue")),
         _yoy(yoy.get("total_revenue"))],
        ["Net Income",
         _cr(inc.get("net_income")),
         _yoy(yoy.get("net_income"))],
        ["Operating Cash Flow",
         _cr(cfs.get("operating_cash_flow")),
         _yoy(yoy.get("operating_cash_flow"))],
    ]

    # Add sector ratios
    for r in ratios.get("sector_ratios", []) + ratios.get("universal_ratios", []):
        metric_rows.append([
            r["label"],
            r["formatted"],
            "—",
        ])

    metrics_table = Table(metric_rows, colWidths=[8*cm, 4.5*cm, 4.5*cm])
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_GRAY, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 0.5*cm))

    # --- Advanced Financial Modeling ---
    if piotroski or altman or dcf:
        story.append(Paragraph("Advanced Financial Modeling", styles["VittaH2"]))
        
        adv_rows = [
            [Paragraph("Model", styles["VittaTableHeader"]),
             Paragraph("Score / Value", styles["VittaTableHeader"]),
             Paragraph("Interpretation", styles["VittaTableHeader"])]
        ]
        
        if piotroski:
            interp = "Average"
            if isinstance(piotroski.get("score"), int):
                if piotroski["score"] >= 7: interp = "Strong Financials"
                elif piotroski["score"] <= 3: interp = "Weak Financials"
            adv_rows.append(["Piotroski F-Score", f"{piotroski.get('score', 'N/A')}/9", interp])
            
        if altman:
            adv_rows.append(["Altman Z-Score", str(altman.get('score', 'N/A')), altman.get('zone', 'N/A')])
            
        if dcf:
            val = dcf.get("intrinsic_value", "N/A")
            if isinstance(val, (int, float)):
                val = f"Rs. {val}"
            margin = dcf.get("margin_of_safety", "N/A")
            if isinstance(margin, (int, float)):
                margin = f"{margin}% Margin of Safety"
            adv_rows.append(["DCF Intrinsic Value", val, margin])
            
        adv_table = Table(adv_rows, colWidths=[6*cm, 4*cm, 7*cm])
        adv_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_GRAY, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("TEXTCOLOR", (0, 1), (-1, -1), TEXT_DARK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(adv_table)
        story.append(Spacer(1, 0.5*cm))

    # --- Trend chart ---
    story.append(Paragraph("Revenue vs Net Income Trend", styles["VittaH2"]))
    try:
        chart_buf = _render_trend_chart(normalized, periods, company_name)
        chart_img = Image(chart_buf, width=16*cm, height=7*cm)
        story.append(chart_img)
    except Exception as e:
        logger.warning("Chart rendering failed: %s", e)
        story.append(Paragraph(f"Chart unavailable: {e}", styles["VittaBody"]))

    story.append(Spacer(1, 1*cm))

    # --- Footer note ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"Data source: Yahoo Finance (yfinance), generated on {today}. "
        "For informational purposes only — not investment advice. "
        "All monetary figures in Rs. Crore.",
        styles["VittaFooter"]
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()
