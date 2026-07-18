import logging
from fastapi import APIRouter, HTTPException
from core.database import get_connection
from core.calculations import calculate_holdings
from core.schemas import TickerUpdate

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
                   tp.currency, COALESCE(tp.intraday_current, tp.price) as price
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
    logger.info("PUT /api/tickers/%d - friendly_name=%s, category=%s", id, ticker.friendly_name, ticker.category)
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
        conn.commit()
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
        return {"status": "success"}
    finally:
        conn.close()
