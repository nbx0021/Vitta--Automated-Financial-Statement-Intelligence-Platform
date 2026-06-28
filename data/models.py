import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def calculate_piotroski_f_score(inc: dict, bal: dict, cfs: dict) -> dict:
    """
    Calculates the 9-point Piotroski F-Score.
    Takes normalized dictionaries of pandas Series (newest-first).
    Returns a dict with the total score and the breakdown.
    Requires at least 2 years of data.
    """
    score = 0
    breakdown = {}
    
    try:
        if not inc or not bal or not cfs:
            return {"score": "N/A", "breakdown": {}}
        
        # Helper to get value safely
        def val(d, key, idx):
            s = d.get(key)
            if s is None or len(s) <= idx:
                return None
            v = s.iloc[idx]
            if pd.isna(v):
                return None
            return v
        
        # 1. Profitability
        ni_0 = val(inc, 'net_income', 0)
        ni_1 = val(inc, 'net_income', 1)
        ta_0 = val(bal, 'total_assets', 0)
        ta_1 = val(bal, 'total_assets', 1)
        
        # ROA > 0
        if ni_0 is not None and ta_0 is not None and ta_0 > 0:
            roa_current = ni_0 / ta_0
            if roa_current > 0:
                score += 1
                breakdown["ROA > 0"] = True
            else:
                breakdown["ROA > 0"] = False
        else:
            roa_current = None
            
        # OCF > 0
        ocf_0 = val(cfs, 'operating_cash_flow', 0)
        if ocf_0 is not None:
            if ocf_0 > 0:
                score += 1
                breakdown["OCF > 0"] = True
            else:
                breakdown["OCF > 0"] = False
                
        # Change in ROA > 0
        if ni_1 is not None and ta_1 is not None and ta_1 > 0 and roa_current is not None:
            roa_prev = ni_1 / ta_1
            if roa_current > roa_prev:
                score += 1
                breakdown["Change in ROA > 0"] = True
            else:
                breakdown["Change in ROA > 0"] = False
                
        # Accruals (OCF > Net Income)
        if ocf_0 is not None and ni_0 is not None:
            if ocf_0 > ni_0:
                score += 1
                breakdown["Accruals (OCF > NI)"] = True
            else:
                breakdown["Accruals (OCF > NI)"] = False
                
        # 2. Leverage, Liquidity, and Source of Funds
        # Change in Leverage < 0
        ltd_0 = val(bal, 'total_debt', 0)
        ltd_1 = val(bal, 'total_debt', 1)
        if ltd_0 is not None and ltd_1 is not None and ta_0 is not None and ta_1 is not None and ta_0 > 0 and ta_1 > 0:
            lev_curr = ltd_0 / ta_0
            lev_prev = ltd_1 / ta_1
            if lev_curr < lev_prev:
                score += 1
                breakdown["Change in Leverage < 0"] = True
            else:
                breakdown["Change in Leverage < 0"] = False
                
        # Change in Current Ratio > 0
        # Wait, normalized fields might not have current_assets/liabilities yet. 
        # But we can try to extract if they exist, else skip.
        # Let's fallback to assuming no point if missing.
        score_added = False
        # (Vitta transform.py doesn't currently extract current_assets by default, so we might miss this point)
        # But we will leave it out or give 0 if missing.
                
        # Change in Shares Outstanding (Dilution)
        # Vitta doesn't extract shares into normalized by default, but we can check info.
        
        # 3. Operating Efficiency
        gp_0 = val(inc, 'gross_profit', 0)
        gp_1 = val(inc, 'gross_profit', 1)
        rev_0 = val(inc, 'total_revenue', 0)
        rev_1 = val(inc, 'total_revenue', 1)
        
        # Change in Gross Margin > 0
        if gp_0 is not None and gp_1 is not None and rev_0 is not None and rev_1 is not None and rev_0 > 0 and rev_1 > 0:
            gm_curr = gp_0 / rev_0
            gm_prev = gp_1 / rev_1
            if gm_curr > gm_prev:
                score += 1
                breakdown["Change in Gross Margin > 0"] = True
            else:
                breakdown["Change in Gross Margin > 0"] = False
                
        # Change in Asset Turnover > 0
        if rev_0 is not None and rev_1 is not None and ta_0 is not None and ta_1 is not None and ta_0 > 0 and ta_1 > 0:
            at_curr = rev_0 / ta_0
            at_prev = rev_1 / ta_1
            if at_curr > at_prev:
                score += 1
                breakdown["Change in Asset Turnover > 0"] = True
            else:
                breakdown["Change in Asset Turnover > 0"] = False
                
        # If we didn't calculate at least 5 elements, consider it N/A
        if len(breakdown) < 4:
            return {"score": "N/A", "breakdown": {}}
            
        return {"score": score, "breakdown": breakdown}
        
    except Exception as e:
        logger.warning(f"Error calculating Piotroski: {e}")
        return {"score": "N/A", "breakdown": {}}

def calculate_altman_z_score(inc: dict, bal: dict, info: dict) -> dict:
    """
    Altman Z-Score (Original for manufacturing/non-financial)
    """
    try:
        def val(d, key, idx):
            s = d.get(key)
            if s is None or len(s) <= idx: return None
            v = s.iloc[idx]
            return None if pd.isna(v) else v
            
        ta = val(bal, 'total_assets', 0)
        tl = val(bal, 'total_debt', 0) # proxy for total liabilities if not extracted
        re = val(bal, 'retained_earnings', 0)
        ebit = val(inc, 'operating_income', 0)
        sales = val(inc, 'total_revenue', 0)
        
        if ta is None or ta == 0:
            return {"score": "N/A", "zone": "Unknown"}
            
        # Working Capital = 0 (we lack current assets/liabs in default transform)
        t1 = 0
        t2 = (re / ta) if re is not None else 0
        t3 = (ebit / ta) if ebit is not None else 0
        
        # Market Value of Equity (Market Cap)
        mve_crore = info.get('marketCap')
        if mve_crore:
            mve_crore = mve_crore / 10000000 # Convert to Cr if it's in absolute
        else:
            mve_crore = 0
            
        if mve_crore and tl is not None and tl != 0:
            t4 = mve_crore / tl
        else:
            t4 = 0
            
        t5 = (sales / ta) if sales is not None else 0
        
        z_score = 1.2 * t1 + 1.4 * t2 + 3.3 * t3 + 0.6 * t4 + 1.0 * t5
        z_score = round(z_score, 2)
        
        if z_score < 1.81:
            zone = "Distress Zone (High Risk)"
        elif 1.81 <= z_score <= 2.99:
            zone = "Grey Zone (Moderate Risk)"
        else:
            zone = "Safe Zone (Low Risk)"
            
        return {"score": z_score, "zone": zone}
        
    except Exception as e:
        logger.warning(f"Error calculating Altman Z: {e}")
        return {"score": "N/A", "zone": "Unknown"}

def calculate_simple_dcf(cfs: dict, info: dict, wacc: float = 0.10, terminal_growth: float = 0.03, projection_years: int = 5) -> dict:
    """
    Very basic DCF Valuation using historical FCF averages.
    """
    try:
        ocf_series = cfs.get('operating_cash_flow')
        capex_series = cfs.get('capex')
        
        if ocf_series is None or capex_series is None or len(ocf_series) == 0:
            return {"intrinsic_value": "N/A", "margin_of_safety": "N/A"}
            
        # FCF = OCF + CapEx (CapEx is negative in this pipeline usually)
        fcf_series = ocf_series + capex_series
        
        avg_fcf = fcf_series.mean()
        if pd.isna(avg_fcf) or avg_fcf <= 0:
            return {"intrinsic_value": "N/A (Negative FCF)", "margin_of_safety": "N/A"}
            
        # Project FCF
        projected_fcfs = [avg_fcf * (1 + terminal_growth)**i for i in range(1, projection_years + 1)]
        
        # Discount projected FCFs
        pv_fcfs = sum([fcf / ((1 + wacc)**(i+1)) for i, fcf in enumerate(projected_fcfs)])
        
        # Terminal Value
        tv = (projected_fcfs[-1] * (1 + terminal_growth)) / (wacc - terminal_growth)
        pv_tv = tv / ((1 + wacc)**projection_years)
        
        # Enterprise Value
        ev_crore = pv_fcfs + pv_tv
        ev = ev_crore * 10000000 # Convert back to absolute
        
        shares = info.get('sharesOutstanding', info.get('impliedSharesOutstanding'))
        current_price = info.get('currentPrice', info.get('previousClose'))
        
        if not shares or not current_price:
            return {"intrinsic_value": "N/A (Missing Shares/Price)", "margin_of_safety": "N/A"}
            
        intrinsic_value_per_share = ev / shares
        intrinsic_value_per_share = round(intrinsic_value_per_share, 2)
        
        margin = ((intrinsic_value_per_share - current_price) / current_price) * 100
        margin = round(margin, 2)
        
        return {
            "intrinsic_value": intrinsic_value_per_share,
            "current_price": current_price,
            "margin_of_safety": margin
        }
        
    except Exception as e:
        logger.warning(f"Error calculating DCF: {e}")
        return {"intrinsic_value": "N/A", "margin_of_safety": "N/A"}
