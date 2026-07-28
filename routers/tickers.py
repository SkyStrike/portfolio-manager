import logging
from fastapi import APIRouter, HTTPException
from core.database import get_connection
from core.calculations import calculate_holdings
from core.schemas import TickerUpdate
from core.cache import clear_dashboard_cache

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/tickers")
def list_tickers():
    logger.info("GET /api/tickers")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Calculate active shares per ticker across all portfolios
        cursor.execute("SELECT id FROM portfolios")
        portfolios = cursor.fetchall()
        ticker_shares = {}
        for p in portfolios:
            holdings = calculate_holdings(p['id'], conn)
            for tid, h in holdings.items():
                ticker_shares[tid] = ticker_shares.get(tid, 0.0) + h['shares']
                
        cursor.execute("""
            SELECT t.id, t.symbol, t.friendly_name, t.tax_rate, t.notes, t.exchange, t.underlying, t.category,
                   tp.currency, COALESCE(tp.intraday_current, tp.price) as price, COALESCE(tp.is_manual, 0) as is_manual,
                   (SELECT COUNT(*) FROM transactions WHERE ticker_id = t.id) +
                   (SELECT COUNT(*) FROM dividends WHERE ticker_id = t.id) as ref_count
            FROM tickers t
            LEFT JOIN ticker_prices tp ON t.id = tp.ticker_id
            ORDER BY t.symbol
        """)
        tickers = []
        for row in cursor.fetchall():
            d = dict(row)
            d['subclass'] = d.get('category') or 'Other'
            d['category'] = d.get('category') or 'Other'
            d['classification'] = 'Other'
            tickers.append(d)
        for t in tickers:
            t['shares'] = ticker_shares.get(t['id'], 0.0)
        return tickers
    finally:
        conn.close()

@router.put("/api/tickers/{id}")
def update_ticker(id: int, ticker: TickerUpdate):
    logger.info("PUT /api/tickers/%d - friendly_name=%s, category=%s, price=%s, is_manual=%s",
                id, ticker.friendly_name, ticker.category, ticker.price, ticker.is_manual)
    conn = get_connection()
    try:
        cat_val = ticker.category or ticker.subclass
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tickers
            SET friendly_name = COALESCE(?, friendly_name),
                tax_rate = COALESCE(?, tax_rate),
                notes = COALESCE(?, notes),
                underlying = COALESCE(?, underlying),
                category = COALESCE(?, category),
                exchange = COALESCE(?, exchange)
            WHERE id = ?
        """, (ticker.friendly_name, ticker.tax_rate, ticker.notes, ticker.underlying, cat_val, ticker.exchange, id))

        # Handle price and is_manual override in ticker_prices
        if ticker.price is not None or ticker.is_manual is not None:
            is_man = 1 if ticker.is_manual else (0 if ticker.is_manual is False else None)
            from datetime import datetime, timezone
            now_str = datetime.now(timezone.utc).isoformat()
            
            cursor.execute("SELECT ticker_id FROM ticker_prices WHERE ticker_id = ?", (id,))
            exists = cursor.fetchone()
            if exists:
                updates = []
                params = []
                if ticker.price is not None:
                    updates.extend(["price = ?", "intraday_current = ?", "daily_close = ?"])
                    params.extend([ticker.price, ticker.price, ticker.price])
                if is_man is not None:
                    updates.append("is_manual = ?")
                    params.append(is_man)
                updates.append("last_updated = ?")
                params.append(now_str)
                params.append(id)
                
                sql = f"UPDATE ticker_prices SET {', '.join(updates)} WHERE ticker_id = ?"
                cursor.execute(sql, tuple(params))
            else:
                p_val = ticker.price or 0.0
                m_val = is_man if is_man is not None else 1
                cursor.execute("""
                    INSERT INTO ticker_prices (ticker_id, price, intraday_current, daily_close, currency, last_updated, is_manual)
                    VALUES (?, ?, ?, ?, 'USD', ?, ?)
                """, (id, p_val, p_val, p_val, now_str, m_val))

        conn.commit()
        from core.cache import rebuild_dashboard_sync
        rebuild_dashboard_sync(conn)
        clear_dashboard_cache()
        return {"status": "success"}
    finally:
        conn.close()

@router.delete("/api/tickers/{id}")
def delete_ticker(id: int):
    logger.info("DELETE /api/tickers/%d", id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Check if ticker has any transactions or dividends
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE ticker_id = ?", (id,))
        tx_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dividends WHERE ticker_id = ?", (id,))
        div_count = cursor.fetchone()[0]
        if tx_count > 0 or div_count > 0:
            raise HTTPException(status_code=400, detail="Cannot delete ticker with active transactions or dividends.")
        
        # Delete from ticker_prices and tickers
        cursor.execute("DELETE FROM ticker_prices WHERE ticker_id = ?", (id,))
        cursor.execute("DELETE FROM tickers WHERE id = ?", (id,))
        conn.commit()
        clear_dashboard_cache()
        return {"status": "success"}
    finally:
        conn.close()
