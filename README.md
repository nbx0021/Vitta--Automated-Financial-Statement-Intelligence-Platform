# Vitta — Automated Financial Statement Intelligence Platform

<div align="center">
  <img alt="Vitta" src="https://img.shields.io/badge/Vitta-Financial%20Intelligence-6366F1?style=for-the-badge" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python" />
  <img alt="Flask" src="https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask" />
  <img alt="yfinance" src="https://img.shields.io/badge/yfinance-only%20data%20source-06B6D4?style=for-the-badge" />
</div>

---

Vitta is a complete, locally-runnable web application for automated financial statement analysis of **NSE-listed Indian companies**. It requires **no API keys** and **no paid services** — just Python packages.

---

## Quick Start

```bash
# 1. Clone or download the project
cd "Vitta  Automated Financial Statement Intelligence Platform"

# 2. (Recommended) Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py

# 5. Open your browser
# http://localhost:5000
```

---

## Architecture

```
vitta/
├── app.py                  Flask entry point, routes, Flask-Caching
├── requirements.txt        All pip dependencies
├── data/
│   ├── fetcher.py          yfinance wrappers — get_income_statement,
│   │                       get_balance_sheet, get_cash_flow, get_company_info
│   ├── transform.py        Currency normalization (raw INR → ₹ Crore),
│   │                       YoY % change calculations, field extraction
│   ├── validation.py       Cross-statement linkage checks
│   ├── sectors.py          Sector classification + ratio engine (config-driven)
│   └── narrative.py        Rule-based analyst narrative generator (no LLM)
├── templates/
│   ├── base.html           Shared layout: nav, fonts, Chart.js CDN
│   ├── index.html          Ticker input / landing page
│   ├── dashboard.html      Full analysis dashboard
│   └── error.html          Friendly error page
├── static/
│   ├── css/style.css       Full design system (dark, fintech aesthetic)
│   └── js/
│       ├── dashboard.js    Chart.js initialization
│       └── connections.js  Connected statements SVG animation engine
└── reports/
    └── generator.py        ReportLab PDF + matplotlib chart embedding
```

### Data Flow

```
User enters ticker
      ↓
fetcher.py  →  raw yfinance DataFrames (income, balance, cashflow, info)
      ↓
transform.py → normalized dicts in ₹ Crore + YoY changes
      ↓
validation.py → cross-statement linkage checks (pass/fail/unable_to_verify)
      ↓
sectors.py  →  sector classification + ratio computation
      ↓
narrative.py → deterministic, template-based analyst note
      ↓
dashboard.html (Jinja2) + Chart.js + connections.js
      ↓  (optionally)
reports/generator.py → ReportLab PDF with matplotlib chart
```

---

## Features

### ✅ Connected Statements Animation
The centerpiece feature: a 2×2 grid of the four financial statements (Income Statement, Balance Sheet, Statement of Changes in Equity, Cash Flow Statement) with **five linkage buttons**:

| Button | What it shows |
|--------|---------------|
| Net Income | IS → CFS (indirect method start) → Equity retained earnings |
| Depreciation | IS D&A line → CFS add-back |
| Working Capital | BS AR/AP → CFS working capital adjustment |
| Dividends | CFS financing → Equity dividends → BS retained earnings |
| Cash Tie-Out | CFS ending cash → BS cash & equivalents |

Clicking a button **highlights the relevant rows** and draws an **animated dashed cubic-bezier SVG line** between them, positioned dynamically from `getBoundingClientRect`. A `ResizeObserver` redraws the lines on window resize.

### ✅ Linkage Validation
Three automated checks with **pass / fail / unable to verify** status:
1. **Cash Tie-Out** — Ending CFS cash ≈ BS Cash & Equivalents (5% tolerance)
2. **Net Income Flow** — IS net income ≈ CFS operating section start
3. **Earnings Quality** — Flags if net income is positive but OCF is negative

### ✅ Sector-Appropriate Ratios
Config-driven sector classification:

| Bucket | Ratios |
|--------|--------|
| Technology / IT | Gross Margin, Revenue Growth |
| Manufacturing / FMCG | Inventory Turnover, Gross Margin, ROA |
| Energy / Telecom | Debt/Equity, CapEx % Revenue, EV/EBITDA |
| Banking / NBFC | Net Interest Margin, ROE, Leverage Ratio |
| All sectors | ROE, ROIC (best-effort), Debt/EBITDA |

Adding a new sector requires **only a dict entry** in `data/sectors.py` — no new code.

### ✅ PDF Reports
- ReportLab Platypus with custom page templates
- matplotlib renders the trend chart → embedded as PNG
- Executive summary callout block, validation table, metrics table
- Proper footer: data source disclosure, date, not-investment-advice note

---

## Data Source: yfinance

**yfinance is the ONLY data source.** No Alpha Vantage, no Financial Modeling Prep, no API keys.

### Known Coverage Limitations for Indian Stocks

| Category | Coverage Notes |
|----------|---------------|
| Large-cap NSE (Nifty 50) | Generally good — 3-4 years of annual statements |
| Mid-cap NSE | Moderate — some fields may be missing or renamed |
| Small-cap NSE | Thin — common to hit "unable to verify" on all three checks |
| Quarterly data | Not used by Vitta (only annual statements) |
| Cash flow ending balance | Often missing → cash tie-out shows "unable to verify" |
| NIM for banks | yfinance doesn't separate interest income from revenue for Indian banks — NIM is a proxy |
| EV/EBITDA | Available only when yfinance populates `enterpriseValue` in company info |

### Field Name Variance
yfinance renames fields across versions and by ticker. `transform.py` uses a **candidate list approach**: each canonical field has an ordered list of possible yfinance labels. The first match wins. If none match, the field returns `None` and the UI shows `—` rather than crashing.

---

## Tested Tickers

| Ticker | Sector | Cash Tie-Out | NI Flow | Earnings Quality |
|--------|--------|:---:|:---:|:---:|
| TCS.NS | Technology | TBD | TBD | TBD |
| RELIANCE.NS | Energy | TBD | TBD | TBD |
| HDFCBANK.NS | Banking | TBD | TBD | TBD |
| TATAMOTORS.NS | Manufacturing | TBD | TBD | TBD |
| INFY.NS | Technology | TBD | TBD | TBD |

*Run the app against each ticker to populate this table — "unable to verify" outcomes indicate yfinance data gaps for that company.*

---

## Configuration

### Caching
`app.py` uses **Flask-Caching SimpleCache** (in-memory, 5-minute TTL). Repeated requests for the same ticker within a session skip the yfinance network call. To disable caching during development:

```python
app.config["CACHE_DEFAULT_TIMEOUT"] = 0
```

### Adding a New Sector
Edit `data/sectors.py`:

```python
SECTOR_MAPPING.append(("your sector string", "my_bucket"))

SECTOR_CONFIG["my_bucket"] = {
    "label": "My New Sector",
    "ratios": ["gross_margin", "return_on_equity"],  # existing ratio names
}
```

No other code changes needed.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | Flask 3.x + Jinja2 |
| Data | yfinance, pandas, numpy |
| Caching | Flask-Caching (SimpleCache) |
| Charts (browser) | Chart.js 4.x via CDN |
| Animations | Vanilla JavaScript + SVG |
| PDF | ReportLab (Platypus) |
| PDF charts | matplotlib (Agg backend) |
| Fonts | Inter + JetBrains Mono (Google Fonts) |

---

## Disclaimer

> Data source: Yahoo Finance (yfinance). All figures are in ₹ Crore.  
> For informational purposes only — **not investment advice**.  
> Accuracy depends on yfinance's data quality for the specific ticker.
