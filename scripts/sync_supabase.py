"""
scripts/sync_supabase.py
========================
Fetches financial data for the top 75 NSE tickers from Yahoo Finance
and upserts them into Supabase. Run this via GitHub Actions cron job.

Key: Uses curl_cffi natively (yfinance >= 0.2.51 supports it),
     which spoofs Chrome's TLS fingerprint to bypass Yahoo's Cloudflare block.
"""
import os
import time
import json
import logging
from typing import Optional

import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

# Set up logging FIRST (needed before any imports that use it)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Setup curl_cffi session ────────────────────────────────────────────────────
# yfinance >= 0.2.51 accepts a raw curl_cffi session via the `session=` kwarg
# on yf.Ticker(). This is the ONLY reliable way to bypass Yahoo Finance's
# Cloudflare TLS fingerprint check on cloud/CI environments.
try:
    from curl_cffi import requests as cffi_requests
    _session = cffi_requests.Session(impersonate="chrome120")
    USE_CFFI = True
    logger.info("Using curl_cffi session (Chrome120 TLS impersonation)")
except ImportError:
    _session = None
    USE_CFFI = False
    logger.warning("curl_cffi not found — falling back to plain requests (may be blocked)")

# Top 75 NSE Tickers (Sector-wise)
TOP_75_TICKERS = [
    # IT / Technology
    "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS",
    "LTIM.NS", "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS",
    # Banking & Finance
    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS",
    "INDUSINDBK.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "CHOLAFIN.NS",
    "MUTHOOTFIN.NS", "SBICARD.NS",
    # FMCG
    "ITC.NS", "HUL.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS",
    "DABUR.NS", "GODREJCP.NS", "MARICO.NS", "COLPAL.NS", "UBL.NS",
    # Auto
    "TATAMOTORS.NS", "M&M.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS",
    "EICHERMOT.NS", "TVSMOTOR.NS", "ASHOKLEY.NS", "BOSCHLTD.NS",
    # Energy & Oil/Gas
    "RELIANCE.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "COALINDIA.NS",
    "BPCL.NS", "IOC.NS", "GAIL.NS", "TATAPOWER.NS", "ADANIGREEN.NS",
    # Pharma & Healthcare
    "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "APOLLOHOSP.NS",
    "LUPIN.NS", "AUROPHARMA.NS", "TORNTPHARM.NS", "BIOCON.NS",
    # Metals & Mining
    "TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "VEDL.NS", "NMDC.NS",
    # Infrastructure & Cement
    "LT.NS", "ULTRACEMCO.NS", "GRASIM.NS", "AMBUJACEM.NS", "SHREECEM.NS", "ACC.NS",
    # Retail & Consumer
    "TITAN.NS", "PAGEIND.NS", "TRENT.NS", "DMART.NS",
]


def _make_ticker(ticker: str):
    """Create a yf.Ticker with curl_cffi session if available."""
    import yfinance as yf
    ticker = ticker.upper()
    if not ticker.endswith(".NS"):
        ticker += ".NS"
    if USE_CFFI and _session is not None:
        return yf.Ticker(ticker, session=_session)
    return yf.Ticker(ticker)


def _df_to_json(df: Optional[pd.DataFrame]) -> dict:
    """Convert a DataFrame (items as rows, periods as columns) to a JSON-safe dict."""
    if df is None or df.empty:
        return {}
    df = df.copy()
    df.index = df.index.astype(str).str.strip()
    try:
        df = df[sorted(df.columns, reverse=True)]
    except TypeError:
        pass
    # Convert Timestamp column names to YYYY-MM-DD strings
    df.columns = [
        c.strftime("%Y-%m-%d") if hasattr(c, "strftime") else str(c).split(" ")[0]
        for c in df.columns
    ]
    return json.loads(df.to_json(orient="index"))


def fetch_and_sync(ticker: str):
    logger.info(f"Syncing data for {ticker}...")
    try:
        t = _make_ticker(ticker)

        # Fetch statements
        inc_df = getattr(t, "income_stmt", None)
        if inc_df is None or (hasattr(inc_df, 'empty') and inc_df.empty):
            inc_df = getattr(t, "financials", None)
            
        bal_df = getattr(t, "balance_sheet", None)
        
        cf_df = getattr(t, "cashflow", None)
        if cf_df is None or (hasattr(cf_df, 'empty') and cf_df.empty):
            cf_df = getattr(t, "cash_flow", None)

        inc_data = _df_to_json(inc_df)
        bal_data = _df_to_json(bal_df)
        cf_data  = _df_to_json(cf_df)

        # Fetch company info (optional — tolerate failure)
        try:
            info = t.info or {}
        except Exception as e:
            logger.warning(f"Could not fetch .info for {ticker}: {e}")
            info = {}

        info_keys = [
            "longName", "shortName", "symbol", "sector", "industry",
            "currency", "exchange", "marketCap", "website",
            "totalDebt", "totalCash", "ebitda", "enterpriseValue",
            "trailingPE", "forwardPE", "priceToBook",
        ]
        info_data = {k: info.get(k) for k in info_keys}

        if not inc_data and not bal_data and not cf_data:
            logger.warning(f"No statement data returned for {ticker} — skipping upsert.")
            return

        payload = {
            "ticker": ticker.upper(),
            "info": info_data,
            "income_statement": inc_data,
            "balance_sheet": bal_data,
            "cash_flow": cf_data,
        }

        supabase.table("financial_data").upsert(payload, on_conflict="ticker").execute()
        logger.info(f"Successfully synced {ticker}")

    except Exception as e:
        import traceback
        logger.error(f"Error syncing {ticker}: {e}")
        logger.error(traceback.format_exc())


def main():
    logger.info("Starting Supabase Sync Job")
    for ticker in TOP_75_TICKERS:
        fetch_and_sync(ticker)
        time.sleep(4)
    logger.info("Sync Job Completed!")


if __name__ == "__main__":
    main()
