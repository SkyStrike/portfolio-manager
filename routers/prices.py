import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from core.database import get_connection
from core.cache import rebuild_dashboard_sync, update_prices_and_rebuild
from services.price_service import update_prices, can_refresh, record_refresh, REFRESH_COOLDOWN

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/api/prices/refresh")
def refresh_prices(background_tasks: BackgroundTasks, force: bool = False):
    logger.info("POST /api/prices/refresh (force=%s)", force)
    if not force and not can_refresh():
        raise HTTPException(
            status_code=429, 
            detail=f"Manual refresh cooldown active. Please wait up to {REFRESH_COOLDOWN.seconds // 60} minutes between refreshes."
        )
        
    if force:
        logger.info("Starting synchronous price refresh...")
        conn = get_connection()
        try:
            update_prices(conn, force=True)
            from services.dividend_service import sync_upcoming_dividends
            try:
                logger.info("Syncing upcoming dividends post price refresh...")
                sync_upcoming_dividends(conn, force=False)
            except Exception as e:
                logger.warning("Failed to sync upcoming dividends in force refresh: %s", e)
            logger.info("Rebuilding dashboard (intraday + closing) after price refresh...")
            rebuild_dashboard_sync(conn, "intraday")
            rebuild_dashboard_sync(conn, "closing")
        finally:
            conn.close()
        record_refresh()
        logger.info("Synchronous price refresh complete.")
        return {"status": "success", "message": "Prices refreshed synchronously."}
    else:
        logger.info("Price refresh queued as background task.")
        background_tasks.add_task(update_prices_and_rebuild)
        record_refresh()
        return {"status": "success", "message": "Price refresh task started in the background."}


# ---------------------------------------------------------------------------
# TX Visualizer – Price History
# ---------------------------------------------------------------------------

_RANGE_CONFIG = {
    "7d":  {"days": 7,    "interval": "1d"},
    "1m":  {"days": 30,   "interval": "1d"},
    "3m":  {"days": 90,   "interval": "1d"},
    "6m":  {"days": 180,  "interval": "1d"},
    "YTD": {"days": None, "interval": "1d"},
    "1y":  {"days": 365,  "interval": "1d"},
    "5y":  {"days": 1825, "interval": "1wk"},
    "all": {"days": 3650, "interval": "1wk"},
}


def _fetch_and_store_history(conn, symbol: str, start_date: str, end_date: str, interval: str, exchange: str = ""):
    """Fetch OHLC data from yfinance and upsert into ticker_price_history."""
    try:
        import yfinance as yf
        from services.price_service import get_yfinance_symbol
        yf_symbol = get_yfinance_symbol(symbol, exchange)
        logger.info("Fetching history for yfinance symbol: %s (DB symbol: %s)", yf_symbol, symbol)
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval, auto_adjust=True)
        if df.empty:
            return 0
        rows = []
        for ts, row in df.iterrows():
            date_str = ts.strftime("%Y-%m-%d")
            rows.append((
                symbol, date_str, interval,
                round(float(row.get("Open", 0) or 0), 6),
                round(float(row.get("High", 0) or 0), 6),
                round(float(row.get("Low",  0) or 0), 6),
                round(float(row.get("Close", 0) or 0), 6),
            ))
        with conn:
            conn.executemany(
                """INSERT OR REPLACE INTO ticker_price_history
                   (symbol, date, interval, open, high, low, close)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        logger.info("Stored %d %s rows for %s (%s to %s)", len(rows), interval, symbol, start_date, end_date)
        return len(rows)
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return 0


@router.get("/api/prices/history/{symbol}")
def get_price_history(
    symbol: str, 
    range: str = Query(default="1y"),
    start: str = Query(default=None),
    end: str = Query(default=None)
):
    """
    Return cached OHLC price history for the TX Visualizer.

    Query params:
        range: one of 7d | 1m | 3m | 6m | YTD | 1y | 5y | all  (default: 1y)
        start: start date string (YYYY-MM-DD) for custom range
        end: end date string (YYYY-MM-DD) for custom range

    Response:
        {
          "symbol": "HYLD-U.TO",
          "interval": "1d",
          "prices": [{"date": "YYYY-MM-DD", "open": x, "high": x, "low": x, "close": x}, ...],
        }
    Transactions and avg_cost are supplied client-side from template data attributes.
    """
    today = datetime.utcnow().date()

    if start and end:
        start_date = start
        end_date = end
        try:
            from datetime import datetime as dt
            start_dt = dt.strptime(start, "%Y-%m-%d").date()
            end_dt = dt.strptime(end, "%Y-%m-%d").date()
            days = (end_dt - start_dt).days
            interval = "1wk" if days > 1095 else "1d"
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid custom date format. Use YYYY-MM-DD")
    else:
        if range not in _RANGE_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid range '{range}'. Choose from: {list(_RANGE_CONFIG)}")

        cfg = _RANGE_CONFIG[range]
        interval = cfg["interval"]
        
        if range == "YTD":
            start_date = datetime(today.year, 1, 1).date().isoformat()
        else:
            start_date = (today - timedelta(days=cfg["days"])).isoformat()
            
        end_date = today.isoformat()

    conn = get_connection()
    try:
        # Get the exchange for this symbol from tickers table
        exchange_row = conn.execute(
            "SELECT exchange FROM tickers WHERE symbol = ?", (symbol,)
        ).fetchone()
        exchange = exchange_row["exchange"] if exchange_row else ""

        # 1. Query what we already have in cache
        rows = conn.execute(
            """SELECT date, open, high, low, close
               FROM ticker_price_history
               WHERE symbol = ? AND interval = ? AND date >= ? AND date <= ?
               ORDER BY date""",
            (symbol, interval, start_date, end_date),
        ).fetchall()

        cached_dates = {r["date"] for r in rows}

        # 2. Gap-fill: if nothing cached OR newest row is stale (> 1 day old), re-fetch
        needs_fetch = False
        if not cached_dates:
            needs_fetch = True
        else:
            newest = max(cached_dates)
            if newest < (today - timedelta(days=1)).isoformat():
                needs_fetch = True

        if needs_fetch:
            # Fetch from newest cached date (or full range for first load)
            fetch_start = max(cached_dates) if cached_dates else start_date
            fetched = _fetch_and_store_history(conn, symbol, fetch_start, end_date, interval, exchange)
            if fetched > 0:
                # Reload from DB after successful fetch
                rows = conn.execute(
                    """SELECT date, open, high, low, close
                       FROM ticker_price_history
                       WHERE symbol = ? AND interval = ? AND date >= ? AND date <= ?
                       ORDER BY date""",
                    (symbol, interval, start_date, end_date),
                ).fetchall()

        prices = [
            {"date": r["date"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"]}
            for r in rows
        ]

        return {
            "symbol": symbol,
            "interval": interval,
            "prices": prices,
        }

    finally:
        conn.close()
