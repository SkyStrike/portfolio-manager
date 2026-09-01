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
    Returns aggregated portfolio metrics (total invested, current value, cash, real gains) grouped by broker.
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
        
        # 1. Fetch cumulative base capital from broker_capital_entries (authoritative source)
        cursor.execute("SELECT UPPER(broker) as broker, SUM(amount) as base_capital FROM broker_capital_entries GROUP BY UPPER(broker)")
        capital_entries_map = {row['broker']: row['base_capital'] for row in cursor.fetchall()}

        # 2. Fetch latest snapshot per broker from daily_cash_report
        cursor.execute("""
            SELECT r.broker, r.date, r.liquidation_value, r.base_capital, r.cash_on_hand, r.total_stock_value
            FROM daily_cash_report r
            INNER JOIN (
                SELECT broker, MAX(date) as max_date
                FROM daily_cash_report
                GROUP BY broker
            ) m ON r.broker = m.broker AND r.date = m.max_date
        """)
        cash_rows = {row['broker'].upper(): dict(row) for row in cursor.fetchall()}
        
        # Query latest price date from ticker_prices
        cursor.execute("SELECT MAX(daily_close_date) FROM ticker_prices")
        latest_price_date = cursor.fetchone()[0]
        
        brokers_data = defaultdict(lambda: {
            "tracking_mode": "stock_holdings_only",
            "last_updated_date": None,
            # Perspective 1: Account & Cash Capital Tracking
            "base_capital_sgd": 0.0,
            "liquidation_value_sgd": 0.0,
            "account_capital_gains_sgd": 0.0,
            "account_capital_gains_pct": 0.0,
            # Perspective 2: Stock Position & Trading Performance
            "stock_cost_basis_sgd": 0.0,
            "current_stock_value_sgd": 0.0,
            "unrealized_pl_sgd": 0.0,
            "realized_pl_sgd": 0.0,
            "dividends_net_sgd": 0.0,
            "total_fees_sgd": 0.0,
            "stock_total_returns_sgd": 0.0,
            "stock_total_returns_pct": 0.0,
            # Cash & Holdings
            "cash_on_hand_sgd": 0.0,
            "portfolios": []
        })
        
        consolidated = {
            "base_capital_sgd": 0.0,
            "liquidation_value_sgd": 0.0,
            "account_capital_gains_sgd": 0.0,
            "account_capital_gains_pct": 0.0,
            "stock_cost_basis_sgd": 0.0,
            "current_stock_value_sgd": 0.0,
            "unrealized_pl_sgd": 0.0,
            "realized_pl_sgd": 0.0,
            "dividends_net_sgd": 0.0,
            "total_fees_sgd": 0.0,
            "stock_total_returns_sgd": 0.0,
            "stock_total_returns_pct": 0.0,
            "total_cash_sgd": 0.0
        }
        
        for p in portfolios:
            br = (p.get("broker") or p["name"]).strip()
            summary = get_portfolio_summary(p["id"], conn, rates, price_mode=price_mode)
            
            inv = summary.get("total_cost_sgd", 0.0)
            fees = summary.get("total_fees_sgd", 0.0)
            val = summary.get("total_value_sgd", 0.0)
            unrealized = summary.get("total_unrealized_pl_sgd", 0.0)
            realized = summary.get("total_realized_pl_sgd", 0.0)
            divs = summary.get("total_dividends_net_sgd", 0.0)
            returns = summary.get("total_profit_sgd", 0.0)
            
            b = brokers_data[br]
            b["stock_cost_basis_sgd"] += inv
            b["total_fees_sgd"] += fees
            b["current_stock_value_sgd"] += val
            b["unrealized_pl_sgd"] += unrealized
            b["realized_pl_sgd"] += realized
            b["dividends_net_sgd"] += divs
            b["stock_total_returns_sgd"] += returns
            
            b["portfolios"].append({
                "id": p["id"],
                "name": p["name"],
                "stock_cost_basis_sgd": round(inv, 2),
                "total_fees_sgd": round(fees, 2),
                "current_stock_value_sgd": round(val, 2),
                "unrealized_pl_sgd": round(unrealized, 2),
                "realized_pl_sgd": round(realized, 2),
                "dividends_net_sgd": round(divs, 2),
                "stock_total_returns_sgd": round(returns, 2)
            })
            
        for br, b_info in brokers_data.items():
            c_info = cash_rows.get(br.upper())
            cap_entry = capital_entries_map.get(br.upper())
            
            if c_info and c_info.get("liquidation_value") is not None:
                b_info["tracking_mode"] = "account_nav_tracked"
                b_info["last_updated_date"] = c_info.get("date")
                b_info["base_capital_sgd"] = round(cap_entry if cap_entry is not None else c_info.get("base_capital", 0.0), 2)
                b_info["liquidation_value_sgd"] = round(c_info.get("liquidation_value", 0.0), 2)
                b_info["cash_on_hand_sgd"] = round(c_info.get("cash_on_hand", 0.0), 2)
            elif cap_entry is not None:
                # User entered explicit base capital into broker_capital_entries (e.g. SRS deposit)
                b_info["tracking_mode"] = "capital_tracked"
                cursor.execute("SELECT MAX(date) FROM broker_capital_entries WHERE UPPER(broker) = ?", (br.upper(),))
                b_info["last_updated_date"] = cursor.fetchone()[0] or latest_price_date
                b_info["base_capital_sgd"] = round(cap_entry, 2)
                # Cash on hand = base capital deposited minus capital spent buying stocks (if positive)
                derived_cash = max(0.0, cap_entry - b_info["stock_cost_basis_sgd"])
                b_info["cash_on_hand_sgd"] = round(derived_cash, 2)
                b_info["liquidation_value_sgd"] = round(b_info["current_stock_value_sgd"] + b_info["cash_on_hand_sgd"], 2)
            else:
                # Automated fallback for stock-only brokers with zero capital entries
                b_info["tracking_mode"] = "stock_holdings_only"
                b_info["last_updated_date"] = latest_price_date
                b_info["base_capital_sgd"] = round(b_info["stock_cost_basis_sgd"], 2)
                b_info["cash_on_hand_sgd"] = 0.0
                b_info["liquidation_value_sgd"] = round(b_info["current_stock_value_sgd"] + b_info["cash_on_hand_sgd"], 2)

            # Perspective 1 Gains
            b_info["account_capital_gains_sgd"] = round(b_info["liquidation_value_sgd"] - b_info["base_capital_sgd"], 2)
            b_info["account_capital_gains_pct"] = round((b_info["account_capital_gains_sgd"] / b_info["base_capital_sgd"] * 100) if b_info["base_capital_sgd"] > 0 else 0.0, 2)
            
            # Perspective 2 Gains
            b_info["stock_total_returns_pct"] = round((b_info["stock_total_returns_sgd"] / b_info["stock_cost_basis_sgd"] * 100) if b_info["stock_cost_basis_sgd"] > 0 else 0.0, 2)
            
            for k in ["stock_cost_basis_sgd", "total_fees_sgd", "current_stock_value_sgd", "unrealized_pl_sgd", "realized_pl_sgd", "dividends_net_sgd", "stock_total_returns_sgd"]:
                b_info[k] = round(b_info[k], 2)
                
            consolidated["base_capital_sgd"] += b_info["base_capital_sgd"]
            consolidated["liquidation_value_sgd"] += b_info["liquidation_value_sgd"]
            consolidated["total_cash_sgd"] += b_info["cash_on_hand_sgd"]
            consolidated["stock_cost_basis_sgd"] += b_info["stock_cost_basis_sgd"]
            consolidated["total_fees_sgd"] += b_info["total_fees_sgd"]
            consolidated["current_stock_value_sgd"] += b_info["current_stock_value_sgd"]
            consolidated["unrealized_pl_sgd"] += b_info["unrealized_pl_sgd"]
            consolidated["realized_pl_sgd"] += b_info["realized_pl_sgd"]
            consolidated["dividends_net_sgd"] += b_info["dividends_net_sgd"]
            consolidated["stock_total_returns_sgd"] += b_info["stock_total_returns_sgd"]

        consolidated["account_capital_gains_sgd"] = round(consolidated["liquidation_value_sgd"] - consolidated["base_capital_sgd"], 2)
        consolidated["account_capital_gains_pct"] = round((consolidated["account_capital_gains_sgd"] / consolidated["base_capital_sgd"] * 100) if consolidated["base_capital_sgd"] > 0 else 0.0, 2)
        consolidated["stock_total_returns_pct"] = round((consolidated["stock_total_returns_sgd"] / consolidated["stock_cost_basis_sgd"] * 100) if consolidated["stock_cost_basis_sgd"] > 0 else 0.0, 2)

        for k in ["base_capital_sgd", "liquidation_value_sgd", "total_cash_sgd", "stock_cost_basis_sgd", "total_fees_sgd", "current_stock_value_sgd", "unrealized_pl_sgd", "realized_pl_sgd", "dividends_net_sgd", "stock_total_returns_sgd"]:
            consolidated[k] = round(consolidated[k], 2)

        return {
            "price_mode": price_mode,
            "brokers": dict(brokers_data),
            "consolidated": consolidated
        }
    finally:
        conn.close()

