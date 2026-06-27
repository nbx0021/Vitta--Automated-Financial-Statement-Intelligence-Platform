import os
import time
import json
import logging
from typing import Optional

import pandas as pd
import yfinance as yf
from supabase import create_client, Client
from dotenv import load_dotenv

import requests

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Custom Session to avoid 429 errors
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

# Top 75 NSE Tickers (Sector-wise)
TOP_75_TICKERS = [
    # IT / Technology
    "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS", "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS",
    # Banking & Finance
    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "INDUSINDBK.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS", "SBICARD.NS",
    # FMCG
    "ITC.NS", "HUL.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS", "DABUR.NS", "GODREJCP.NS", "MARICO.NS", "COLPAL.NS", "UBL.NS",
    # Auto
    "TATAMOTORS.NS", "M&M.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS", "EICHERMOT.NS", "TVSMOTOR.NS", "ASHOKLEY.NS", "BOSCHLTD.NS",
    # Energy & Oil/Gas
    "RELIANCE.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "COALINDIA.NS", "BPCL.NS", "IOC.NS", "GAIL.NS", "TATAPOWER.NS", "ADANIGREEN.NS",
    # Pharma & Healthcare
    "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "APOLLOHOSP.NS", "LUPIN.NS", "AUROPHARMA.NS", "TORNTPHARM.NS", "BIOCON.NS",
    # Metals & Mining
    "TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "VEDL.NS", "NMDC.NS",
    # Infrastructure & Cement
    "LT.NS", "ULTRACEMCO.NS", "GRASIM.NS", "AMBUJACEM.NS", "SHREECEM.NS", "ACC.NS",
    # Retail & Consumer
    "TITAN.NS", "PAGEIND.NS", "TRENT.NS", "DMART.NS"
]


def _safe_ticker(ticker: str) -> yf.Ticker:
    if not ticker.upper().endswith(".NS"):
        ticker = ticker.upper() + ".NS"
    return yf.Ticker(ticker.upper(), session=session)



def _transpose_and_clean(df: Optional[pd.DataFrame]) -> dict:
    if df is None or df.empty:
        return {}
    df = df.copy()
    df.index = df.index.astype(str).str.strip()
    try:
        df = df[sorted(df.columns, reverse=True)]
    except TypeError:
        pass
    
    # Convert column names (timestamps) to strings (YYYY-MM-DD)
    df.columns = [str(col).split(' ')[0] if hasattr(col, 'strftime') else str(col) for col in df.columns]
    
    # Convert to dict with orient='index' to keep row -> period mapping
    return json.loads(df.to_json(orient="index"))


def fetch_and_sync(ticker: str):
    logger.info(f"Syncing data for {ticker}...")
    try:
        t = _safe_ticker(ticker)
        
        # Income Statement
        inc_df = t.income_stmt if hasattr(t, "income_stmt") else t.financials
        inc_data = _transpose_and_clean(inc_df)
        
        # Balance Sheet
        bal_df = t.balance_sheet
        bal_data = _transpose_and_clean(bal_df)
        
        # Cash Flow
        cf_df = t.cashflow if hasattr(t, "cashflow") else t.cash_flow
        cf_data = _transpose_and_clean(cf_df)
        
        # Company Info
        info = t.info or {}
        keys = [
            "longName", "shortName", "symbol", "sector", "industry",
            "currency", "exchange", "marketCap", "website",
            "totalDebt", "totalCash", "ebitda", "enterpriseValue",
            "trailingPE", "forwardPE", "priceToBook",
        ]
        info_data = {k: info.get(k) for k in keys}
        
        # Prepare payload
        payload = {
            "ticker": ticker.upper(),
            "info": info_data,
            "income_statement": inc_data,
            "balance_sheet": bal_data,
            "cash_flow": cf_data
        }
        
        # Upsert into Supabase
        response = supabase.table("financial_data").upsert(payload, on_conflict="ticker").execute()
        logger.info(f"Successfully synced {ticker}")
        
    except Exception as e:
        logger.error(f"Error syncing {ticker}: {e}")

def main():
    logger.info("Starting Supabase Sync Job")
    for ticker in TOP_75_TICKERS:
        fetch_and_sync(ticker)
        time.sleep(4)  # Avoid hammering yfinance too hard
    logger.info("Sync Job Completed!")

if __name__ == "__main__":
    main()
