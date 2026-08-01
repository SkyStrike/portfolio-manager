import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from core.database import get_connection
from core.schemas import ManualPriceOverride
from core.cache import rebuild_dashboard_sync, update_prices_and_rebuild
from services.price_service import update_prices, can_refresh, record_refresh, REFRESH_COOLDOWN

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/api/prices/refresh")
def refresh_prices(background_tasks: BackgroundTasks = None, force: bool = False, sync: bool = True):
    logger.info("POST /api/prices/refresh (force=%s, sync=%s)", force, sync)
    if not force and not can_refresh():
        raise HTTPException(
            status_code=429, 
            detail=f"Manual refresh cooldown active. Please wait up to {REFRESH_COOLDOWN.seconds // 60} minutes between refreshes."
        )
        
    if sync or force:
        logger.info("Starting synchronous price refresh (force=%s)...", force)
        conn = get_connection()
        try:
            update_prices(conn, force=force)
            from services.dividend_service import sync_upcoming_dividends
            try:
                logger.info("Syncing upcoming dividends post price refresh...")
                sync_upcoming_dividends(conn, force=False)
            except Exception as e:
                logger.warning("Failed to sync upcoming dividends in price refresh: %s", e)
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
        if background_tasks:
            background_tasks.add_task(update_prices_and_rebuild)
        record_refresh()
        return {"status": "success", "message": "Price refresh task started in the background."}


@router.get("/api/prices/history-log/{symbol}")
def get_price_history_log(symbol: str, limit: int = 15):
    """
    Returns recent price history log for a symbol from ticker_price_history,
    including is_manual flag and computed daily percentage change.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, date, interval, open, high, low, close, adj_close, COALESCE(is_manual, 0) as is_manual
            FROM ticker_price_history
            WHERE symbol = ? AND interval = '1d'
            ORDER BY date DESC
            LIMIT ?
        """, (symbol, limit))
        rows = [dict(r) for r in cursor.fetchall()]
        
        # Calculate daily change between consecutive rows
        for i in range(len(rows)):
            if i < len(rows) - 1:
                prev_c = rows[i + 1]["close"]
                curr_c = rows[i]["close"]
                rows[i]["daily_pct"] = ((curr_c - prev_c) / prev_c * 100) if prev_c > 0 else 0.0
            else:
                rows[i]["daily_pct"] = 0.0
                
        return {"status": "success", "symbol": symbol, "history": rows}
    finally:
        conn.close()


def _sync_ticker_prices_from_history(conn, symbol: str, ticker_id: int):
    """Syncs ticker_prices snapshot from the 2 latest bars in ticker_price_history."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, close FROM ticker_price_history
        WHERE symbol = ? AND interval = '1d'
        ORDER BY date DESC LIMIT 2
    """, (symbol,))
    bars = cursor.fetchall()
    if not bars:
        return
        
    latest_bar = bars[0]
    prev_bar = bars[1] if len(bars) > 1 else latest_bar
    
    price_val = float(latest_bar["close"])
    prev_val = float(prev_bar["close"])
    date_str = latest_bar["date"]
    prev_date_str = prev_bar["date"]
    now_iso = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("SELECT ticker_id FROM ticker_prices WHERE ticker_id = ?", (ticker_id,))
    if cursor.fetchone():
        cursor.execute("""
            UPDATE ticker_prices
            SET price = ?,
                intraday_current = ?,
                daily_close = ?,
                intraday_prev_close = ?,
                daily_prev_close = ?,
                intraday_current_at = ?,
                daily_close_date = ?,
                intraday_prev_close_date = ?,
                daily_prev_close_date = ?,
                last_updated = ?
            WHERE ticker_id = ?
        """, (price_val, price_val, price_val, prev_val, prev_val,
              now_iso, date_str, prev_date_str, prev_date_str, now_iso, ticker_id))
    else:
        cursor.execute("""
            INSERT INTO ticker_prices (ticker_id, price, intraday_current, daily_close, intraday_prev_close, daily_prev_close, currency, last_updated, daily_close_date, daily_prev_close_date)
            VALUES (?, ?, ?, ?, ?, ?, 'USD', ?, ?, ?)
        """, (ticker_id, price_val, price_val, price_val, prev_val, prev_val, now_iso, date_str, prev_date_str))


@router.post("/api/prices/manual-history")
def save_manual_price_history(payload: ManualPriceOverride):
    """
    Saves or updates a manual price entry (date, price) in ticker_price_history with is_manual=1,
    then updates ticker_prices if latest date, and rebuilds dashboard cache.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Resolve symbol & ticker_id
        symbol = payload.symbol
        ticker_id = payload.ticker_id
        
        if not symbol and ticker_id:
            cursor.execute("SELECT symbol FROM tickers WHERE id = ?", (ticker_id,))
            t_row = cursor.fetchone()
            if t_row:
                symbol = t_row["symbol"]
        elif symbol and not ticker_id:
            cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
            t_row = cursor.fetchone()
            if t_row:
                ticker_id = t_row["id"]
                
        if not symbol or not ticker_id:
            raise HTTPException(status_code=404, detail="Ticker symbol or ID not found")
            
        price_val = round(float(payload.price), 3)
        date_str = payload.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # 1. Check if existing row exists to preserve OHLC bar structure
        cursor.execute("""
            SELECT open, high, low, close, adj_close 
            FROM ticker_price_history 
            WHERE symbol = ? AND date = ? AND interval = '1d'
        """, (symbol, date_str))
        existing = cursor.fetchone()

        if existing and dict(existing).get("open") is not None:
            ex_open = existing["open"]
            ex_high = max(existing["high"] or price_val, price_val)
            ex_low = min(existing["low"] or price_val, price_val)
            ex_close = existing["close"]
            ex_adj = existing["adj_close"]
            
            # Maintain split/dividend adjustment factor for adj_close if present
            if ex_close and ex_close > 0 and ex_adj is not None:
                new_adj = round((ex_adj / ex_close) * price_val, 6)
            else:
                new_adj = price_val

            cursor.execute("""
                INSERT OR REPLACE INTO ticker_price_history (symbol, date, interval, open, high, low, close, adj_close, is_manual)
                VALUES (?, ?, '1d', ?, ?, ?, ?, ?, 1)
            """, (symbol, date_str, ex_open, ex_high, ex_low, price_val, new_adj))
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO ticker_price_history (symbol, date, interval, open, high, low, close, adj_close, is_manual)
                VALUES (?, ?, '1d', ?, ?, ?, ?, ?, 1)
            """, (symbol, date_str, price_val, price_val, price_val, price_val, price_val))

        # 2. Sync latest price snapshot to ticker_prices
        _sync_ticker_prices_from_history(conn, symbol, ticker_id)

        conn.commit()
        
        # 3. Rebuild dashboard cache
        rebuild_dashboard_sync(conn, "intraday")
        rebuild_dashboard_sync(conn, "closing")
        
        return {"status": "success", "symbol": symbol, "price": price_val, "date": date_str}
    finally:
        conn.close()


@router.delete("/api/prices/manual-history/{symbol}/{date}")
def delete_manual_price_history(symbol: str, date: str):
    """
    Deletes a specific price history entry from ticker_price_history,
    resyncs ticker_prices snapshot, and rebuilds dashboard cache.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
        t_row = cursor.fetchone()
        if not t_row:
            raise HTTPException(status_code=404, detail="Ticker not found")
        ticker_id = t_row["id"]
        
        cursor.execute("DELETE FROM ticker_price_history WHERE symbol = ? AND date = ?", (symbol, date))
        _sync_ticker_prices_from_history(conn, symbol, ticker_id)
        conn.commit()
        
        rebuild_dashboard_sync(conn, "intraday")
        rebuild_dashboard_sync(conn, "closing")
        
        return {"status": "success", "symbol": symbol, "deleted_date": date}
    finally:
        conn.close()


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
        df = ticker.history(start=start_date, end=end_date, interval=interval, auto_adjust=False)
        if df.empty:
            return 0
        rows = []
        for ts, row in df.iterrows():
            date_str = ts.strftime("%Y-%m-%d")
            raw_close = round(float(row.get("Close", 0) or 0), 6)
            adj_close = round(float(row.get("Adj Close", raw_close) or raw_close), 6)
            rows.append((
                symbol, date_str, interval,
                round(float(row.get("Open", 0) or 0), 6),
                round(float(row.get("High", 0) or 0), 6),
                round(float(row.get("Low",  0) or 0), 6),
                raw_close,
                adj_close
            ))
        # Fetch existing manual dates to avoid overwriting user entries
        cursor = conn.cursor()
        cursor.execute("SELECT date FROM ticker_price_history WHERE symbol = ? AND is_manual = 1", (symbol,))
        manual_dates = {r["date"] for r in cursor.fetchall()}
        
        filtered_rows = [r for r in rows if r[1] not in manual_dates]
        
        if filtered_rows:
            with conn:
                conn.executemany(
                    """INSERT OR REPLACE INTO ticker_price_history
                       (symbol, date, interval, open, high, low, close, adj_close, is_manual)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    filtered_rows,
                )
        logger.info("Stored %d %s rows for %s (%s to %s) [skipped %d manual dates]", len(filtered_rows), interval, symbol, start_date, end_date, len(rows) - len(filtered_rows))
        return len(filtered_rows)
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return 0


@router.get("/api/prices/history/{symbol}")
def get_price_history(
    symbol: str, 
    range: str = Query(default="1y"),
    adjusted: bool = Query(default=False),
    start: str = Query(default=None),
    end: str = Query(default=None)
):
    """
    Return cached OHLC price history for the TX Visualizer.

    Query params:
        range: one of 7d | 1m | 3m | 6m | YTD | 1y | 5y | all  (default: 1y)
        adjusted: bool whether to return total-return adjusted prices (default: False, i.e., nominal prices matching execution trades)
        start: start date string (YYYY-MM-DD) for custom range
        end: end date string (YYYY-MM-DD) for custom range

    Response:
        {
          "symbol": "HYLD-U.TO",
          "interval": "1d",
          "adjusted": false,
          "prices": [{"date": "YYYY-MM-DD", "open": x, "high": x, "low": x, "close": x}, ...],
        }
    Transactions and avg_cost are supplied client-side from template data attributes.
    """
    today = datetime.now(timezone.utc).date()

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

        # 1. Query what we already have in cache for this symbol & interval
        cached_rows = conn.execute(
            """SELECT date FROM ticker_price_history
               WHERE symbol = ? AND interval = ?""",
            (symbol, interval),
        ).fetchall()

        cached_dates = {r["date"] for r in cached_rows}
        min_cached = min(cached_dates) if cached_dates else None
        max_cached = max(cached_dates) if cached_dates else None

        # 2. Gap-fill backward if requested start_date is earlier than min_cached
        if not min_cached or min_cached > start_date:
            fetch_end = min_cached if min_cached else end_date
            _fetch_and_store_history(conn, symbol, start_date, fetch_end, interval, exchange)

        # 3. Gap-fill forward if max_cached is stale
        if not max_cached or max_cached < (today - timedelta(days=1)).isoformat():
            fetch_start = max_cached if max_cached else start_date
            _fetch_and_store_history(conn, symbol, fetch_start, end_date, interval, exchange)

        # 4. Fetch final range from DB
        rows = conn.execute(
            """SELECT date, open, high, low, close, adj_close
               FROM ticker_price_history
               WHERE symbol = ? AND interval = ? AND date >= ? AND date <= ?
               ORDER BY date""",
            (symbol, interval, start_date, end_date),
        ).fetchall()

        prices = []
        last_valid_close = None
        last_valid_adj_close = None

        for r in rows:
            raw_c = r["close"]
            adj_c = r["adj_close"]

            # Forward-fill if raw_c is None or 0.0
            if (raw_c is None or raw_c == 0.0) and last_valid_close is not None:
                raw_c = last_valid_close
                adj_c = last_valid_adj_close if last_valid_adj_close is not None else raw_c
            elif raw_c is not None and raw_c > 0.0:
                last_valid_close = raw_c
                last_valid_adj_close = adj_c

            raw_c = raw_c or 0.0
            adj_c = adj_c if adj_c is not None else raw_c

            if adjusted and raw_c > 0 and adj_c > 0:
                factor = adj_c / raw_c
                prices.append({
                    "date": r["date"],
                    "open": round((r["open"] or raw_c) * factor, 4),
                    "high": round((r["high"] or raw_c) * factor, 4),
                    "low": round((r["low"] or raw_c) * factor, 4),
                    "close": round(adj_c, 4)
                })
            else:
                prices.append({
                    "date": r["date"],
                    "open": r["open"] or raw_c,
                    "high": r["high"] or raw_c,
                    "low": r["low"] or raw_c,
                    "close": raw_c
                })

        return {
            "symbol": symbol,
            "interval": interval,
            "adjusted": adjusted,
            "prices": prices,
        }

    finally:
        conn.close()
