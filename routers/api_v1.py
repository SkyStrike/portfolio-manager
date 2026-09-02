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

        from datetime import datetime
        return {
            "generated_at": datetime.now().isoformat(),
            "as_of_date": latest_price_date,
            "price_mode": price_mode,
            "brokers": dict(brokers_data),
            "consolidated": consolidated
        }
    finally:
        conn.close()


@router.get("/reports/tag-exposure")
def get_tag_exposure_report(price_mode: str = Query("closing")):
    """
    Returns cross-portfolio tag exposure breakdown, including market values, cost basis,
    unrealized gains, total returns, and portfolio percentage weights in SGD.
    """
    logger.info("GET /api/v1/reports/tag-exposure (price_mode=%s)", price_mode)
    from datetime import datetime
    from collections import defaultdict
    from core.database import get_connection
    from core.calculations import calculate_holdings
    from services.fetch_exchange_rates import get_exchange_rates

    conn = get_connection()
    try:
        cursor = conn.cursor()
        rates = get_exchange_rates()
        usd_rate = rates.get("USD", 1.0)
        cad_rate = rates.get("CAD", 1.0)

        cursor.execute("SELECT id, name, broker FROM portfolios ORDER BY sort_order ASC, name ASC")
        portfolios = [dict(r) for r in cursor.fetchall()]

        # Latest price date
        cursor.execute("SELECT MAX(daily_close_date) FROM ticker_prices")
        latest_price_date = cursor.fetchone()[0]

        # Ticker metadata and prices
        cursor.execute("""
            SELECT t.id, t.symbol, t.friendly_name, t.category, t.underlying, t.exchange,
                   tp.currency, tp.daily_close, tp.intraday_current, tp.daily_prev_close, tp.intraday_prev_close
            FROM tickers t
            LEFT JOIN ticker_prices tp ON t.id = tp.ticker_id
        """)
        ticker_info = {r["id"]: dict(r) for r in cursor.fetchall()}

        # Ticker tags mapping
        cursor.execute("""
            SELECT tt.ticker_id, tg.id as tag_id, tg.name, tg.color
            FROM ticker_tags tt
            JOIN tags tg ON tt.tag_id = tg.id
            ORDER BY tg.name ASC
        """)
        ticker_to_tags = defaultdict(list)
        for r in cursor.fetchall():
            ticker_to_tags[r["ticker_id"]].append({"id": r["tag_id"], "name": r["name"], "color": r["color"]})

        # Lifetime Realized P&L and fees in SGD per ticker
        cursor.execute("""
            SELECT ticker_id,
                   SUM(COALESCE(realized_pl_sgd, 0.0)) as realized_pl_sgd,
                   SUM(COALESCE(commission, 0.0) * CASE WHEN currency = 'SGD' THEN 1.0 WHEN currency = 'USD' THEN ? WHEN currency = 'CAD' THEN ? ELSE 1.0 END) as total_fees_sgd
            FROM transactions
            GROUP BY ticker_id
        """, (usd_rate, cad_rate))
        tx_stats = {r["ticker_id"]: dict(r) for r in cursor.fetchall()}

        # Lifetime Net Dividends in SGD per ticker
        cursor.execute("""
            SELECT ticker_id,
                   SUM((amount - tax) * CASE WHEN currency = 'SGD' THEN 1.0 WHEN currency = 'USD' THEN ? WHEN currency = 'CAD' THEN ? ELSE 1.0 END) as dividends_net_sgd
            FROM dividends
            GROUP BY ticker_id
        """, (usd_rate, cad_rate))
        div_stats = {r["ticker_id"]: dict(r) for r in cursor.fetchall()}

        # Aggregate active holdings across portfolios
        ticker_holdings = defaultdict(lambda: {
            "total_shares": 0.0,
            "total_cost_basis_native": 0.0,
            "portfolios": []
        })

        for p in portfolios:
            h_map = calculate_holdings(p["id"], conn)
            for tid, h in h_map.items():
                if h["shares"] > 0:
                    c_basis = h["shares"] * h["avg_cost"]
                    ticker_holdings[tid]["total_shares"] += h["shares"]
                    ticker_holdings[tid]["total_cost_basis_native"] += c_basis
                    ticker_holdings[tid]["portfolios"].append({
                        "portfolio_id": p["id"],
                        "portfolio_name": p["name"],
                        "broker": p["broker"] or "",
                        "shares": round(h["shares"], 4),
                        "cost_basis_native": round(c_basis, 2)
                    })

        all_active_tickers = {}
        total_portfolio_value_sgd = 0.0
        total_portfolio_cost_sgd = 0.0
        total_portfolio_unrealized_sgd = 0.0
        total_portfolio_realized_sgd = 0.0
        total_portfolio_dividends_sgd = 0.0
        total_portfolio_returns_sgd = 0.0

        for tid, h in ticker_holdings.items():
            info = ticker_info.get(tid, {})
            curr = info.get("currency") or "USD"
            rate = rates.get(curr, 1.0)
            
            if price_mode == "closing":
                price = info.get("daily_close") if info.get("daily_close") is not None else (info.get("intraday_current") or 0.0)
            else:
                price = info.get("intraday_current") if info.get("intraday_current") is not None else (info.get("daily_close") or 0.0)

            shares = h["total_shares"]
            cost_native = h["total_cost_basis_native"]
            market_val_sgd = shares * price * rate
            cost_basis_sgd = cost_native * rate
            unrealized_pl_sgd = market_val_sgd - cost_basis_sgd
            unrealized_pl_pct = (unrealized_pl_sgd / cost_basis_sgd * 100) if cost_basis_sgd > 0 else 0.0

            realized_pl_sgd = tx_stats.get(tid, {}).get("realized_pl_sgd", 0.0)
            total_fees_sgd = tx_stats.get(tid, {}).get("total_fees_sgd", 0.0)
            dividends_net_sgd = div_stats.get(tid, {}).get("dividends_net_sgd", 0.0)
            total_returns_sgd = unrealized_pl_sgd + realized_pl_sgd + dividends_net_sgd - total_fees_sgd
            total_returns_pct = (total_returns_sgd / cost_basis_sgd * 100) if cost_basis_sgd > 0 else 0.0

            tag_objs = ticker_to_tags.get(tid, [])

            t_obj = {
                "ticker_id": tid,
                "symbol": info.get("symbol", ""),
                "friendly_name": info.get("friendly_name", ""),
                "category": info.get("category", "Other"),
                "underlying": info.get("underlying", ""),
                "exchange": info.get("exchange", ""),
                "currency": curr,
                "price": round(price, 4),
                "shares": round(shares, 4),
                "market_value_sgd": round(market_val_sgd, 2),
                "cost_basis_sgd": round(cost_basis_sgd, 2),
                "unrealized_pl_sgd": round(unrealized_pl_sgd, 2),
                "unrealized_pl_pct": round(unrealized_pl_pct, 2),
                "realized_pl_sgd": round(realized_pl_sgd, 2),
                "dividends_net_sgd": round(dividends_net_sgd, 2),
                "total_returns_sgd": round(total_returns_sgd, 2),
                "total_returns_pct": round(total_returns_pct, 2),
                "tags": [t["name"] for t in tag_objs],
                "portfolios": h["portfolios"]
            }
            all_active_tickers[tid] = t_obj
            total_portfolio_value_sgd += market_val_sgd
            total_portfolio_cost_sgd += cost_basis_sgd
            total_portfolio_unrealized_sgd += unrealized_pl_sgd
            total_portfolio_realized_sgd += realized_pl_sgd
            total_portfolio_dividends_sgd += dividends_net_sgd
            total_portfolio_returns_sgd += total_returns_sgd

        # Group by tags
        cursor.execute("SELECT id, name, color FROM tags ORDER BY name ASC")
        all_tags = [dict(r) for r in cursor.fetchall()]

        tag_reports = []
        for tag in all_tags:
            t_name = tag["name"]
            matching_tickers = [t for t in all_active_tickers.values() if t_name in t["tags"]]
            if not matching_tickers:
                continue

            tag_val = sum(t["market_value_sgd"] for t in matching_tickers)
            tag_cost = sum(t["cost_basis_sgd"] for t in matching_tickers)
            tag_unrealized = sum(t["unrealized_pl_sgd"] for t in matching_tickers)
            tag_unrealized_pct = (tag_unrealized / tag_cost * 100) if tag_cost > 0 else 0.0
            tag_realized = sum(t["realized_pl_sgd"] for t in matching_tickers)
            tag_dividends = sum(t["dividends_net_sgd"] for t in matching_tickers)
            tag_returns = sum(t["total_returns_sgd"] for t in matching_tickers)
            tag_returns_pct = (tag_returns / tag_cost * 100) if tag_cost > 0 else 0.0
            portfolio_weight_pct = (tag_val / total_portfolio_value_sgd * 100) if total_portfolio_value_sgd > 0 else 0.0

            ticker_list = []
            for t in sorted(matching_tickers, key=lambda x: x["market_value_sgd"], reverse=True):
                t_copy = dict(t)
                t_copy["tag_weight_pct"] = round((t["market_value_sgd"] / tag_val * 100) if tag_val > 0 else 0.0, 2)
                t_copy["portfolio_weight_pct"] = round((t["market_value_sgd"] / total_portfolio_value_sgd * 100) if total_portfolio_value_sgd > 0 else 0.0, 2)
                ticker_list.append(t_copy)

            tag_reports.append({
                "id": tag["id"],
                "name": t_name,
                "color": tag["color"],
                "ticker_count": len(matching_tickers),
                "total_market_value_sgd": round(tag_val, 2),
                "total_cost_basis_sgd": round(tag_cost, 2),
                "total_unrealized_pl_sgd": round(tag_unrealized, 2),
                "total_unrealized_pl_pct": round(tag_unrealized_pct, 2),
                "total_realized_pl_sgd": round(tag_realized, 2),
                "total_dividends_net_sgd": round(tag_dividends, 2),
                "total_returns_sgd": round(tag_returns, 2),
                "total_returns_pct": round(tag_returns_pct, 2),
                "portfolio_weight_pct": round(portfolio_weight_pct, 2),
                "tickers": ticker_list
            })

        tag_reports.sort(key=lambda x: x["total_market_value_sgd"], reverse=True)

        # All tickers formatted for "All Tickers" view
        all_tickers_list = []
        for t in sorted(all_active_tickers.values(), key=lambda x: x["market_value_sgd"], reverse=True):
            t_copy = dict(t)
            t_copy["tag_weight_pct"] = round((t["market_value_sgd"] / total_portfolio_value_sgd * 100) if total_portfolio_value_sgd > 0 else 0.0, 2)
            t_copy["portfolio_weight_pct"] = t_copy["tag_weight_pct"]
            all_tickers_list.append(t_copy)

        return {
            "generated_at": datetime.now().isoformat(),
            "as_of_date": latest_price_date,
            "price_mode": price_mode,
            "total_portfolio_value_sgd": round(total_portfolio_value_sgd, 2),
            "total_portfolio_cost_sgd": round(total_portfolio_cost_sgd, 2),
            "total_portfolio_unrealized_sgd": round(total_portfolio_unrealized_sgd, 2),
            "total_portfolio_unrealized_pct": round((total_portfolio_unrealized_sgd / total_portfolio_cost_sgd * 100) if total_portfolio_cost_sgd > 0 else 0.0, 2),
            "total_portfolio_realized_sgd": round(total_portfolio_realized_sgd, 2),
            "total_portfolio_dividends_sgd": round(total_portfolio_dividends_sgd, 2),
            "total_portfolio_returns_sgd": round(total_portfolio_returns_sgd, 2),
            "total_portfolio_returns_pct": round((total_portfolio_returns_sgd / total_portfolio_cost_sgd * 100) if total_portfolio_cost_sgd > 0 else 0.0, 2),
            "tags": tag_reports,
            "all_tickers": all_tickers_list
        }
    finally:
        conn.close()

