import sqlite3
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.database import DB_FILE
from core.cache import rebuild_dashboard_sync

logger = logging.getLogger(__name__)

def patch(params: dict = None):
    """
    Finds tickers whose exchange was on holiday or untraded during recent market sessions
    (where daily_close_date is older than the max daily_close_date in the database)
    and sets intraday_prev_close = intraday_current and daily_prev_close = daily_close.
    """
    print("[Patch 0004] Starting holiday/untraded ticker price P/L reset...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # 1. Find the latest daily_close_date across all tickers
        cursor.execute("SELECT MAX(daily_close_date) FROM ticker_prices WHERE daily_close_date IS NOT NULL")
        row = cursor.fetchone()
        max_date = row[0] if row else None
        
        if not max_date:
            print("[Patch 0004] No daily_close_date found in database. Exiting.")
            return {"status": "success", "message": "No price dates found in database."}
            
        print(f"[Patch 0004] Latest market date in database: {max_date}")
        
        # 2. Query untraded / holiday tickers where daily_close_date < max_date
        cursor.execute("""
            SELECT tp.ticker_id, t.symbol, tp.intraday_current, tp.daily_close, tp.daily_close_date
            FROM ticker_prices tp
            JOIN tickers t ON tp.ticker_id = t.id
            WHERE tp.daily_close_date < ? OR tp.daily_close_date IS NULL
        """, (max_date,))
        
        stale_rows = cursor.fetchall()
        print(f"[Patch 0004] Found {len(stale_rows)} tickers untraded/on holiday relative to max date '{max_date}'.")
        
        updated_count = 0
        for ticker_id, symbol, intraday_curr, daily_cls, close_date in stale_rows:
            curr_val = intraday_curr or 0.0
            close_val = daily_cls or curr_val
            
            cursor.execute("""
                UPDATE ticker_prices
                SET intraday_prev_close = ?,
                    daily_prev_close = ?
                WHERE ticker_id = ?
            """, (curr_val, close_val, ticker_id))
            updated_count += 1
            print(f"  -> Reset P/L base for '{symbol}' (last close date: {close_date}): daily P/L set to 0.0")
            
        conn.commit()
        print(f"[Patch 0004] Successfully updated {updated_count} untraded/holiday tickers.")
        
        # 3. Trigger cache rebuild so dashboard P/L is updated immediately
        print("[Patch 0004] Rebuilding dashboard cache...")
        rebuild_dashboard_sync()
        print("[Patch 0004] Cache rebuild complete.")
        
        return {
            "status": "success",
            "message": f"Successfully reset P/L base for {updated_count} untraded/holiday tickers relative to {max_date}."
        }
    except Exception as e:
        conn.rollback()
        print(f"[Patch 0004] Error executing patch: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    patch()
