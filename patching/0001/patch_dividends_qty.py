import sqlite3
import os
import sys

# Setup import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.database import get_connection
from core.calculations import get_shares_on_date

def patch(params: dict = None):
    print("Starting dividend qty patching...")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, portfolio_id, ticker_id, date, amount, notes FROM dividends WHERE qty IS NULL")
        rows = cursor.fetchall()
        print(f"Found {len(rows)} records needing patching.")
        
        updates = []
        for r in rows:
            qty = get_shares_on_date(r['portfolio_id'], r['ticker_id'], r['date'][:10], conn)
            updates.append((qty, r['id']))
            print(f"ID {r['id']}: Date={r['date'][:10]}, calculated qty={qty}")
            
        if updates:
            cursor.executemany("UPDATE dividends SET qty = ? WHERE id = ?", updates)
            conn.commit()
            print("Successfully updated all records.")
        else:
            print("No records updated.")
    finally:
        conn.close()

if __name__ == '__main__':
    patch()
