import sys
sys.path.insert(0, "/app")
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

def patch(params: dict = None):
    """
    Truncates all transaction and dividend timestamps in portfolio.db to date-only strings (YYYY-MM-DD),
    recalculates holdings running cost basis/realized PnL, and rebuilds dashboard views.
    """
    db_path = os.getenv("PORTFOLIO_DB_FILE", "data/portfolio.db")
    if not os.path.exists(db_path):
        logger.warning("Database file not found at %s. Skipping patch.", db_path)
        return

    from core.database import get_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Truncate transactions date to YYYY-MM-DD
        cursor.execute("UPDATE transactions SET date = SUBSTR(date, 1, 10) WHERE LENGTH(date) > 10")
        tx_patched = cursor.rowcount
        
        # 2. Truncate dividends date to YYYY-MM-DD
        cursor.execute("UPDATE dividends SET date = SUBSTR(date, 1, 10) WHERE LENGTH(date) > 10")
        div_patched = cursor.rowcount
        
        # 3. Recalculate cost basis and realized PnL across all portfolios
        cursor.execute("SELECT id FROM portfolios")
        portfolio_ids = [row['id'] for row in cursor.fetchall()]
        
        from core.calculations import calculate_holdings
        for pid in portfolio_ids:
            calculate_holdings(pid, conn)
            
        conn.commit()
        
        # 4. Trigger dashboard rebuild
        from core.cache import rebuild_dashboard_sync
        rebuild_dashboard_sync(conn)
        
        logger.info("Patch 0002 completed: %d transactions and %d dividends date strings cleaned to YYYY-MM-DD.", tx_patched, div_patched)
    finally:
        conn.close()

if __name__ == "__main__":
    patch()
