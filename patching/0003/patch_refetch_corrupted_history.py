import os
import sys
import logging
from datetime import datetime, timezone, timedelta

# Setup import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.database import get_connection
from routers.prices import _sync_ticker_prices_from_history
from services.price_service import get_yfinance_symbol
from core.cache import rebuild_dashboard_sync

logger = logging.getLogger(__name__)

def patch_symbol_history(conn, symbol: str, start_date: str, end_date: str, interval: str = "1d", exchange: str = ""):
    """
    Fetch OHLC history from yfinance for a symbol.
    ONLY updates/repairs rows in ticker_price_history where open == high == low == close (flat/corrupted bars).
    Leaves valid non-flat historical bars untouched.
    For manual entries (is_manual = 1), preserves the manually entered nominal 'close' price
    while updating open, high, low, and adj_close from yfinance.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, close, is_manual 
            FROM ticker_price_history 
            WHERE symbol = ? AND interval = ?
              AND open = high AND high = low AND low = close
        """, (symbol, interval))
        flat_rows = {r["date"]: dict(r) for r in cursor.fetchall()}

        if not flat_rows:
            return 0

        import yfinance as yf
        yf_symbol = get_yfinance_symbol(symbol, exchange)
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval, auto_adjust=False)
        if df.empty:
            return 0

        history_rows = []
        for ts, row in df.iterrows():
            date_str = ts.strftime("%Y-%m-%d")
            # ONLY repair/update rows that are actually flat in the database
            if date_str not in flat_rows:
                continue

            target_flat_row = flat_rows[date_str]
            raw_close = round(float(row.get("Close", 0) or 0), 6)
            adj_close = round(float(row.get("Adj Close", raw_close) or raw_close), 6)
            open_val = round(float(row.get("Open", 0) or 0), 6)
            high_val = round(float(row.get("High", 0) or 0), 6)
            low_val = round(float(row.get("Low", 0) or 0), 6)

            if target_flat_row.get("is_manual") == 1:
                # Preserve user's manual nominal close price
                manual_close = target_flat_row["close"]
                history_rows.append((
                    symbol, date_str, interval,
                    open_val, high_val, low_val,
                    manual_close,
                    adj_close,
                    1
                ))
            else:
                history_rows.append((
                    symbol, date_str, interval,
                    open_val, high_val, low_val,
                    raw_close,
                    adj_close,
                    0
                ))

        if history_rows:
            with conn:
                conn.executemany("""
                    INSERT OR REPLACE INTO ticker_price_history
                    (symbol, date, interval, open, high, low, close, adj_close, is_manual)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, history_rows)
        return len(history_rows)
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return 0

def patch(params: dict = None):
    print("Starting price history corruption refetch patch (flat bars only)...")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Identify symbols with flat OHLC rows (open=high=low=close)
        cursor.execute("""
            SELECT DISTINCT t.id, t.symbol, t.exchange 
            FROM tickers t
            JOIN ticker_price_history h ON t.symbol = h.symbol
            WHERE h.open = h.high 
              AND h.high = h.low 
              AND h.low = h.close
        """)
        tickers_to_refetch = [dict(r) for r in cursor.fetchall()]
        print(f"Found {len(tickers_to_refetch)} tickers with flat OHLC history bars.")
        
        today = datetime.now(timezone.utc).date()
        start_date = (today - timedelta(days=365)).isoformat()
        end_date = today.isoformat()
        
        success_count = 0
        for t in tickers_to_refetch:
            symbol = t['symbol']
            exchange = t['exchange'] or ''
            ticker_id = t['id']
            print(f"Refetching OHLC history for {symbol} ({exchange})...")
            
            count = patch_symbol_history(conn, symbol, start_date, end_date, interval="1d", exchange=exchange)
            if count > 0:
                _sync_ticker_prices_from_history(conn, symbol, ticker_id)
                success_count += 1
                
        print(f"Successfully refetched and updated {success_count}/{len(tickers_to_refetch)} tickers.")
        
        # 3. Rebuild dashboard cache
        print("Rebuilding dashboard views...")
        rebuild_dashboard_sync(conn)
        print("Patch 0003 complete!")
        
    finally:
        conn.close()

if __name__ == '__main__':
    patch()
