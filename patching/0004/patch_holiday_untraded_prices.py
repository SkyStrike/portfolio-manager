import sqlite3
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.database import DB_FILE
from core.cache import rebuild_dashboard_sync

logger = logging.getLogger(__name__)

CANADIAN_EXCHANGES = {"TO", "V", "TSX", "TSX-V", "NEO", "CSE"}

def patch(params: dict = None):
    """
    Exchange-aware P/L base price reset:
    - Restores latest and previous close prices from ticker_price_history per exchange.
    - For Canadian tickers on Canadian exchange holidays (e.g. 2026-08-03 Civic Holiday),
      sets daily_prev_close = daily_close (0 P/L change on holiday).
    - For SGX and US tickers operating on regular market sessions, compares latest close
      against previous session close.
    """
    print("[Patch 0004] Executing exchange-aware P/L base price fix...")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT t.id, t.symbol, t.exchange
            FROM tickers t
        """)
        tickers = cursor.fetchall()
        
        updated_count = 0
        holiday_count = 0
        
        for r in tickers:
            tid = r['id']
            sym = r['symbol']
            exc = (r['exchange'] or "").strip().upper()
            is_canadian = (exc in CANADIAN_EXCHANGES) or sym.endswith(".TO") or sym.endswith(".V")
            
            cursor.execute("""
                SELECT date, close FROM ticker_price_history
                WHERE symbol = ? ORDER BY date DESC LIMIT 2
            """, (sym,))
            history = cursor.fetchall()
            
            if len(history) >= 2:
                latest = history[0]
                prev = history[1]
                
                # Check if Canadian stock untraded on Canadian Civic Holiday (Aug 3 2026)
                if is_canadian and latest['date'] < '2026-08-03':
                    intraday_prev = latest['close']
                    daily_prev = latest['close']
                    holiday_count += 1
                else:
                    intraday_prev = prev['close']
                    daily_prev = prev['close']
                    
                cursor.execute("""
                    UPDATE ticker_prices
                    SET price = ?,
                        intraday_current = ?,
                        intraday_prev_close = ?,
                        daily_close = ?,
                        daily_prev_close = ?,
                        daily_close_date = ?,
                        daily_prev_close_date = ?
                    WHERE ticker_id = ?
                """, (latest['close'], latest['close'], intraday_prev, latest['close'], daily_prev, latest['date'], prev['date'], tid))
                updated_count += 1
                
        conn.commit()
        print(f"[Patch 0004] Successfully updated {updated_count} tickers ({holiday_count} Canadian tickers set to 0.0 P/L for Aug 3 holiday).")
        
        print("[Patch 0004] Rebuilding dashboard cache...")
        rebuild_dashboard_sync()
        print("[Patch 0004] Cache rebuild complete.")
        
        return {
            "status": "success",
            "message": f"Successfully updated {updated_count} tickers with exchange-aware P/L baselines."
        }
    except Exception as e:
        conn.rollback()
        print(f"[Patch 0004] Error executing patch: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    patch()
