"""
data/fetcher.py
===============
Reads financial data from Supabase instead of yfinance.
Returns data exactly as expected by the pipeline (pandas DataFrames).
"""
import os
import logging
import pandas as pd
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load env variables and initialize Supabase
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.warning("SUPABASE_URL or SUPABASE_KEY not found in environment. Data fetch will fail.")
    supabase: Optional[Client] = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def _safe_ticker(ticker: str) -> str:
    """Ensure .NS suffix."""
    ticker = ticker.upper()
    if not ticker.endswith(".NS"):
        ticker += ".NS"
    return ticker

def _fetch_from_supabase(ticker: str) -> dict:
    """Helper to fetch a ticker's full payload from Supabase."""
    if not supabase:
        raise ConnectionError("Supabase client not initialized. Check your .env file.")
    
    t = _safe_ticker(ticker)
    
    try:
        response = supabase.table("financial_data").select("*").eq("ticker", t).execute()
        data = response.data
        if not data:
            raise ValueError(
                f"No financial data returned for '{ticker}'. "
                "Please verify the ticker is a valid NSE symbol and is synced in the database."
            )
        return data[0]
    except ValueError as ve:
        raise ve
    except Exception as e:
        logger.error(f"Supabase fetch error for {t}: {e}")
        raise ConnectionError(f"Failed to connect to database: {e}")

def _dict_to_df(data: dict) -> pd.DataFrame:
    """Convert the stored JSON (orient='index') back to the expected DataFrame format."""
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(data, orient="index")
    # Sort columns descending
    try:
        df = df[sorted(df.columns, reverse=True)]
    except TypeError:
        pass
    return df

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_income_statement(ticker: str) -> pd.DataFrame:
    """Fetch the annual income statement from Supabase."""
    try:
        data = _fetch_from_supabase(ticker)
        return _dict_to_df(data.get("income_statement", {}))
    except Exception as exc:
        logger.warning(f"get_income_statement({ticker}) failed: {exc}")
        if isinstance(exc, ConnectionError) or isinstance(exc, ValueError):
            raise exc
        return pd.DataFrame()

def get_balance_sheet(ticker: str) -> pd.DataFrame:
    """Fetch the annual balance sheet from Supabase."""
    try:
        data = _fetch_from_supabase(ticker)
        return _dict_to_df(data.get("balance_sheet", {}))
    except Exception as exc:
        logger.warning(f"get_balance_sheet({ticker}) failed: {exc}")
        if isinstance(exc, ConnectionError) or isinstance(exc, ValueError):
            raise exc
        return pd.DataFrame()

def get_cash_flow(ticker: str) -> pd.DataFrame:
    """Fetch the annual cash flow statement from Supabase."""
    try:
        data = _fetch_from_supabase(ticker)
        return _dict_to_df(data.get("cash_flow", {}))
    except Exception as exc:
        logger.warning(f"get_cash_flow({ticker}) failed: {exc}")
        if isinstance(exc, ConnectionError) or isinstance(exc, ValueError):
            raise exc
        return pd.DataFrame()

def get_company_info(ticker: str) -> dict:
    """Fetch company metadata from Supabase."""
    try:
        data = _fetch_from_supabase(ticker)
        return data.get("info", {})
    except Exception as exc:
        logger.warning(f"get_company_info({ticker}) failed: {exc}")
        if isinstance(exc, ConnectionError) or isinstance(exc, ValueError):
            raise exc
        return {}

def get_all_data(ticker: str) -> dict:
    """
    Since we fetch all data at once from Supabase anyway, 
    we can optimize this convenience wrapper to only do one network call.
    """
    try:
        payload = _fetch_from_supabase(ticker)
        return {
            "income": _dict_to_df(payload.get("income_statement", {})),
            "balance": _dict_to_df(payload.get("balance_sheet", {})),
            "cashflow": _dict_to_df(payload.get("cash_flow", {})),
            "info": payload.get("info", {})
        }
    except Exception as exc:
        logger.warning(f"get_all_data({ticker}) failed: {exc}")
        if isinstance(exc, ConnectionError) or isinstance(exc, ValueError):
            raise exc
        return {
            "income": pd.DataFrame(),
            "balance": pd.DataFrame(),
            "cashflow": pd.DataFrame(),
            "info": {}
        }
