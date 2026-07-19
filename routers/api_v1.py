import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from core.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["v1"])

def _get_raw_data(price_mode: str):
    from core.cache import _dashboard_cache, get_cached_view
    cache_key = "closing" if price_mode == "closing" else "intraday"
    if not _dashboard_cache[cache_key]:
        get_cached_view("portfolio_active.html", cache_key)
    data = _dashboard_cache[cache_key].get("src/portfolio_data.json")
    if not data or not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="Portfolio data cache empty")
    return data

@router.get("/portfolios/positions")
def get_positions(
    classification: Optional[str] = Query(None),
    portfolio_id: Optional[int] = Query(None),
    price_mode: str = Query("closing")
):
    """Fetch position list dynamically for active/closed views without loading full JSON blob."""
    logger.info("GET /api/v1/portfolios/positions (classification=%s, portfolio_id=%s, price_mode=%s)", classification, portfolio_id, price_mode)
    data = _get_raw_data(price_mode)
    
    positions = data.get("positions", [])
    if classification:
        positions = [p for p in positions if p.get("classification") == classification]
    if portfolio_id:
        positions = [p for p in positions if p.get("portfolio_id") == portfolio_id]
        
    return {
        "price_mode": price_mode,
        "count": len(positions),
        "positions": positions,
        "dashboard": data.get("dashboard", {})
    }

@router.get("/portfolios/summary")
def get_summary_kpis(price_mode: str = Query("closing")):
    """Fetch high-level KPIs (Total MV, Invested, Lifetime PnL), config, and update datetimes."""
    logger.info("GET /api/v1/portfolios/summary (price_mode=%s)", price_mode)
    data = _get_raw_data(price_mode)
    metadata = data.get("metadata", {})
    return {
        "price_mode": price_mode,
        "summary": metadata.get("summary", {}),
        "config": metadata.get("config", {}),
        "quotes_last_updated_sgt": metadata.get("quotes_last_updated_sgt"),
        "ib_report_datetime_sgt": metadata.get("ib_report_datetime_sgt")
    }

@router.get("/reports/performance")
def get_performance_report(price_mode: str = Query("closing")):
    """Fetch performance report data and chart series dynamically."""
    logger.info("GET /api/v1/reports/performance (price_mode=%s)", price_mode)
    from core.performance_calculator import get_performance_report_data
    from services.generate_performance_report import build_chart_data
    import os
    
    db_path = os.getenv("PORTFOLIO_DB_FILE", "data/portfolio.db")
    data = get_performance_report_data(db_path)
    
    years = data["years"]
    classifications = data["classifications"]
    cash_by_year_month = data["cash_data"]
    portfolio_by_class_year_month = data["portfolio_data"]
    
    chart_data = build_chart_data(years, cash_by_year_month, portfolio_by_class_year_month, data.get("broker_cash_data"))
    
    return {
        "price_mode": price_mode,
        "years": years,
        "classifications": sorted(list(classifications)),
        "cash_data": cash_by_year_month,
        "portfolio_data": portfolio_by_class_year_month,
        "cash_ytd": data["cash_ytd"],
        "portfolio_ytd": dict(data["portfolio_ytd"]),
        "broker_cash_data": data.get("broker_cash_data", {}),
        "broker_cash_ytd": data.get("broker_cash_ytd", {}),
        "chart_data": chart_data
    }

@router.get("/reports/dividend-calendar")
def get_dividend_calendar_report(price_mode: str = Query("closing")):
    """Fetch dividend calendar data and metrics dynamically."""
    logger.info("GET /api/v1/reports/dividend-calendar (price_mode=%s)", price_mode)
    from core.cache import _dashboard_cache, get_cached_view
    cache_key = "closing" if price_mode == "closing" else "intraday"
    if not _dashboard_cache[cache_key]:
        get_cached_view("portfolio_active.html", cache_key)
    cal_data = _dashboard_cache[cache_key].get("src/dividend_calendar_data.json")
    if not cal_data:
        raise HTTPException(status_code=500, detail="Dividend calendar data empty")
    return cal_data
