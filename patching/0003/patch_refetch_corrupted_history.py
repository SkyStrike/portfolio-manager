import os
import sys

# Setup import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.database import get_connection
from routers.prices import _fetch_and_store_history, _sync_ticker_prices_from_history
from core.cache import rebuild_dashboard_sync

def patch(params: dict = None):
    print("Starting price history corruption refetch patch...")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Identify symbols with corrupted OHLC rows (open=high=low=close and is_manual=0)
        cursor.execute("""
            SELECT DISTINCT t.id, t.symbol, t.exchange 
            FROM tickers t
            JOIN ticker_price_history h ON t.symbol = h.symbol
            WHERE h.is_manual = 0 
              AND h.open = h.high 
              AND h.high = h.low 
              AND h.low = h.close
        """)
        tickers_to_refetch = [dict(r) for r in cursor.fetchall()]
        print(f"Found {len(tickers_to_refetch)} tickers with corrupted OHLC history bars.")
        
        # 2. Refetch full 1y history for each corrupted symbol (preserving is_manual=1 rows)
        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone.utc).date()
        start_date = (today - timedelta(days=365)).isoformat()
        end_date = today.isoformat()
        
        success_count = 0
        for t in tickers_to_refetch:
            symbol = t['symbol']
            exchange = t['exchange'] or ''
            ticker_id = t['id']
            print(f"Refetching OHLC history for {symbol} ({exchange})...")
            
            # _fetch_and_store_history automatically preserves is_manual = 1 entries
            count = _fetch_and_store_history(conn, symbol, start_date, end_date, interval="1d", exchange=exchange)
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
