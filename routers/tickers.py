import logging
from fastapi import APIRouter, HTTPException
from core.database import get_connection
from core.calculations import calculate_holdings
from core.schemas import TickerUpdate
from core.cache import clear_dashboard_cache

logger = logging.getLogger(__name__)

router = APIRouter()

from collections import defaultdict

@router.get("/api/tags")
def list_tags():
    """List all available tags with usage counts."""
    logger.info("GET /api/tags")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tg.id, tg.name, tg.color, COUNT(tt.ticker_id) as count
            FROM tags tg
            LEFT JOIN ticker_tags tt ON tg.id = tt.tag_id
            GROUP BY tg.id, tg.name
            ORDER BY tg.name ASC
        """)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

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
                
        # Fetch tags mapping
        cursor.execute("""
            SELECT tt.ticker_id, tg.name
            FROM ticker_tags tt
            JOIN tags tg ON tt.tag_id = tg.id
            ORDER BY tg.name ASC
        """)
        ticker_tags_map = defaultdict(list)
        for r in cursor.fetchall():
            ticker_tags_map[r['ticker_id']].append(r['name'])

        cursor.execute("""
            SELECT t.id, t.symbol, t.friendly_name, t.tax_rate, t.notes, t.exchange, t.underlying, t.category,
                   tp.currency, COALESCE(tp.intraday_current, tp.price) as price,
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
            d['tags'] = ticker_tags_map.get(d['id'], [])
            tickers.append(d)
        for t in tickers:
            t['shares'] = ticker_shares.get(t['id'], 0.0)
        return tickers
    finally:
        conn.close()

@router.put("/api/tickers/{id}")
def update_ticker(id: int, ticker: TickerUpdate):
    logger.info("PUT /api/tickers/%d - friendly_name=%s, category=%s, price=%s, tags=%s",
                id, ticker.friendly_name, ticker.category, ticker.price, ticker.tags)
    conn = get_connection()
    try:
        cat_val = ticker.category or ticker.subclass
        cursor = conn.cursor()
        
        # Handle tags sync if provided
        notes_val = ticker.notes
        if ticker.tags is not None:
            clean_tags = [t.strip().lower() for t in ticker.tags if t.strip()]
            cursor.execute("DELETE FROM ticker_tags WHERE ticker_id = ?", (id,))
            for tag_name in clean_tags:
                cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
                cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_row = cursor.fetchone()
                if tag_row:
                    cursor.execute("INSERT OR IGNORE INTO ticker_tags (ticker_id, tag_id) VALUES (?, ?)", (id, tag_row[0]))
            # Also keep notes in sync with tag string if notes wasn't explicitly changed
            if notes_val is None:
                notes_val = ", ".join(clean_tags)

        cursor.execute("""
            UPDATE tickers
            SET friendly_name = COALESCE(?, friendly_name),
                tax_rate = COALESCE(?, tax_rate),
                notes = COALESCE(?, notes),
                underlying = COALESCE(?, underlying),
                category = COALESCE(?, category),
                exchange = COALESCE(?, exchange)
            WHERE id = ?
        """, (ticker.friendly_name, ticker.tax_rate, notes_val, ticker.underlying, cat_val, ticker.exchange, id))

        # Handle price override in ticker_prices
        if ticker.price is not None:
            from datetime import datetime, timezone
            now_str = datetime.now(timezone.utc).isoformat()
            
            cursor.execute("SELECT ticker_id FROM ticker_prices WHERE ticker_id = ?", (id,))
            exists = cursor.fetchone()
            if exists:
                cursor.execute("""
                    UPDATE ticker_prices
                    SET price = ?, intraday_current = ?, daily_close = ?, last_updated = ?
                    WHERE ticker_id = ?
                """, (ticker.price, ticker.price, ticker.price, now_str, id))
            else:
                cursor.execute("""
                    INSERT INTO ticker_prices (ticker_id, price, intraday_current, daily_close, currency, last_updated)
                    VALUES (?, ?, ?, ?, 'USD', ?)
                """, (id, ticker.price, ticker.price, ticker.price, now_str))

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
