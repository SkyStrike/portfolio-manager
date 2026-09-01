import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from core.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["v1"])

def _get_raw_data(price_mode: str):
    from core.cache import get_cached_portfolio_data
    data = get_cached_portfolio_data(price_mode)
    if not data:
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
        "dashboard": data.get("dashboard", {}),
        "cash_report": data.get("cash_report", {}),
        "open_options": data.get("open_options", []),
        "recent_closed_options": data.get("recent_closed_options", {})
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
    from services.performance_report_service import build_chart_data
    import os
    
    db_path = os.getenv("PORTFOLIO_DB_FILE", "data/portfolio.db")
    data = get_performance_report_data(db_path)
    
    years = data["years"]
    classifications = data["classifications"]
    cash_by_year_month = data["cash_data"]
    portfolio_by_class_year_month = data["portfolio_data"]
    
    chart_data = build_chart_data(
        years, 
        cash_by_year_month, 
        portfolio_by_class_year_month, 
        data.get("broker_cash_data"),
        daily_cash_series=data.get("daily_cash_series"),
        daily_broker_cash_series=data.get("daily_broker_series")
    )
    
    return {
        "price_mode": price_mode,
        "years": years,
        "classifications": sorted(list(classifications)),
        "classification_groups": data.get("classification_groups", []),
        "individual_portfolios": data.get("individual_portfolios", []),
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
    from core.cache import get_cached_dividend_calendar
    cal_data = get_cached_dividend_calendar(price_mode)
    if not cal_data:
        raise HTTPException(status_code=500, detail="Dividend calendar data empty")
    return cal_data

@router.get("/reports/broker-summary")
def get_broker_summary_report(price_mode: str = Query("closing")):
    """
    Returns aggregated portfolio metrics (total invested, current value, cash) grouped by broker.
    Defaults to closing prices.
    """
    logger.info("GET /api/v1/reports/broker-summary (price_mode=%s)", price_mode)
    from core.database import get_connection
    from core.calculations import get_portfolio_summary
    from services.fetch_exchange_rates import get_exchange_rates
    from collections import defaultdict
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, broker FROM portfolios ORDER BY sort_order ASC, name ASC")
        portfolios = [dict(r) for r in cursor.fetchall()]
        rates = get_exchange_rates()
        
        # Fetch latest cash on hand per broker from daily_cash_report
        cursor.execute("""
            SELECT r.broker, r.cash_on_hand
            FROM daily_cash_report r
            INNER JOIN (
                SELECT broker, MAX(date) as max_date
                FROM daily_cash_report
                GROUP BY broker
            ) m ON r.broker = m.broker AND r.date = m.max_date
        """)
        cash_map = {row['broker'].upper(): row['cash_on_hand'] or 0.0 for row in cursor.fetchall()}
        
        brokers_data = defaultdict(lambda: {
            "total_invested_sgd": 0.0,
            "total_fees_sgd": 0.0,
            "current_stock_value_sgd": 0.0,
            "cash_on_hand_sgd": 0.0,
            "total_net_worth_sgd": 0.0,
            "portfolios": []
        })
        
        consolidated = {
            "total_invested_sgd": 0.0,
            "total_fees_sgd": 0.0,
            "current_stock_value_sgd": 0.0,
            "total_cash_sgd": 0.0,
            "total_net_worth_sgd": 0.0
        }
        
        for p in portfolios:
            br = (p.get("broker") or p["name"]).strip()
            summary = get_portfolio_summary(p["id"], conn, rates, price_mode=price_mode)
            
            inv = summary.get("total_cost_sgd", 0.0)
            fees = summary.get("total_fees_sgd", 0.0)
            val = summary.get("total_value_sgd", 0.0)
            
            brokers_data[br]["total_invested_sgd"] += inv
            brokers_data[br]["total_fees_sgd"] += fees
            brokers_data[br]["current_stock_value_sgd"] += val
            brokers_data[br]["portfolios"].append({
                "id": p["id"],
                "name": p["name"],
                "total_invested_sgd": round(inv, 2),
                "total_fees_sgd": round(fees, 2),
                "current_stock_value_sgd": round(val, 2)
            })
            
            consolidated["total_invested_sgd"] += inv
            consolidated["total_fees_sgd"] += fees
            consolidated["current_stock_value_sgd"] += val
            
        for br, b_info in brokers_data.items():
            b_info["cash_on_hand_sgd"] = round(cash_map.get(br.upper(), 0.0), 2)
            b_info["total_net_worth_sgd"] = round(b_info["current_stock_value_sgd"] + b_info["cash_on_hand_sgd"], 2)
            b_info["total_invested_sgd"] = round(b_info["total_invested_sgd"], 2)
            b_info["total_fees_sgd"] = round(b_info["total_fees_sgd"], 2)
            b_info["current_stock_value_sgd"] = round(b_info["current_stock_value_sgd"], 2)
            consolidated["total_cash_sgd"] += b_info["cash_on_hand_sgd"]
            
        consolidated["total_net_worth_sgd"] = round(consolidated["current_stock_value_sgd"] + consolidated["total_cash_sgd"], 2)
        consolidated["total_invested_sgd"] = round(consolidated["total_invested_sgd"], 2)
        consolidated["total_fees_sgd"] = round(consolidated["total_fees_sgd"], 2)
        consolidated["current_stock_value_sgd"] = round(consolidated["current_stock_value_sgd"], 2)
        consolidated["total_cash_sgd"] = round(consolidated["total_cash_sgd"], 2)
        
        return {
            "price_mode": price_mode,
            "brokers": dict(brokers_data),
            "consolidated": consolidated
        }
    finally:
        conn.close()

