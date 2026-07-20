import json
import os
import re
from datetime import datetime
from core.performance_calculator import get_performance_report_data

def slugify(text):
    """Generates URL-safe IDs for HTML anchors and TOC linking."""
    if not text: return ""
    text = str(text).lower()
    text = re.sub(r'[^\w\s\-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

def build_chart_data(years, cash_data, portfolio_data, broker_cash_data=None):
    raw_chart = {
        "cash": {},
        "portfolio": {},
        "broker_cash": {}
    }
    
    def r2(val):
        if val is None:
            return None
        try:
            return round(float(val), 2)
        except:
            return val
            
    # 1. Cash chart data
    for y in years:
        y_data = cash_data.get(y, {})
        raw_chart["cash"][y] = {
            "cumulative": [r2(y_data.get(m, {}).get("base_capital_gains")) for m in range(1, 13)],
            "mtd_val": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_val")) for m in range(1, 13)],
            "mtd_pct": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_pct")) for m in range(1, 13)],
            "mtm_val": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_val")) for m in range(1, 13)],
            "mtm_pct": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_pct")) for m in range(1, 13)]
        }
        
    # 2. Portfolio chart data
    for cls, cls_data in portfolio_data.items():
        raw_chart["portfolio"][cls] = {}
        for y in years:
            y_data = cls_data.get(y, {})
            raw_chart["portfolio"][cls][y] = {
                "cumulative": [r2(y_data.get(m, {}).get("total_returns")) for m in range(1, 13)],
                "mtd_val": [r2(y_data.get(m, {}).get("mtd", {}).get("total_returns_val")) for m in range(1, 13)],
                "mtd_pct": [r2(y_data.get(m, {}).get("mtd", {}).get("total_returns_pct")) for m in range(1, 13)],
                "mtm_val": [r2(y_data.get(m, {}).get("mtm", {}).get("total_returns_val")) for m in range(1, 13)],
                "mtm_pct": [r2(y_data.get(m, {}).get("mtm", {}).get("total_returns_pct")) for m in range(1, 13)]
            }
            
    # 3. Broker cash chart data
    if broker_cash_data:
        for br, br_data in broker_cash_data.items():
            raw_chart["broker_cash"][br] = {}
            for y in years:
                y_data = br_data.get(y, {})
                raw_chart["broker_cash"][br][y] = {
                    "cumulative": [r2(y_data.get(m, {}).get("base_capital_gains")) for m in range(1, 13)],
                    "mtd_val": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_val")) for m in range(1, 13)],
                    "mtd_pct": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_pct")) for m in range(1, 13)],
                    "mtm_val": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_val")) for m in range(1, 13)],
                    "mtm_pct": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_pct")) for m in range(1, 13)]
                }
            
    return raw_chart


