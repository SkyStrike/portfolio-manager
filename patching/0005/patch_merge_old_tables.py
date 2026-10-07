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
    Merges historical benchmark records from daily_cash_report_old into daily_cash_report
    and drops legacy daily_cash_report_old and daily_portfolio_metrics_old tables.
    """
    print("[Patch 0005] Executing merge of old tables...")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 1. Check if daily_cash_report_old exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_cash_report_old'")
        if cursor.fetchone():
            cursor.execute("""
                INSERT OR IGNORE INTO daily_cash_report (date, broker, liquidation_value, base_capital, total_stock_value, cash_on_hand)
                SELECT date, 'CONSOLIDATED', liquidation_value, base_capital, total_stock_value, cash_on_hand
                FROM daily_cash_report_old
                WHERE date NOT IN (SELECT DISTINCT date FROM daily_cash_report)
            """)
            inserted_count = cursor.rowcount
            print(f"[Patch 0005] Merged {inserted_count} historical rows from daily_cash_report_old.")
            cursor.execute("DROP TABLE daily_cash_report_old")
            print("[Patch 0005] Dropped table daily_cash_report_old.")

        # 2. Check if daily_portfolio_metrics_old exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_portfolio_metrics_old'")
        if cursor.fetchone():
            cursor.execute("DROP TABLE daily_portfolio_metrics_old")
            print("[Patch 0005] Dropped table daily_portfolio_metrics_old.")

        conn.commit()
        print("[Patch 0005] Database tables cleaned successfully.")
    except Exception as e:
        conn.rollback()
        print(f"[Patch 0005] ERROR: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    patch()
