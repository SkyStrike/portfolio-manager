import logging
from fastapi import APIRouter, HTTPException
from core.database import get_connection
from core.schemas import PortfolioCreate, PortfolioUpdate, PortfoliosReorder
from core.cache import rebuild_dashboard_sync

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/portfolios")
def list_portfolios():
    logger.info("GET /api/portfolios")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, sort_order, classification, broker FROM portfolios ORDER BY sort_order ASC, name ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@router.post("/api/portfolios")
def create_portfolio(portfolio: PortfolioCreate):
    logger.info("POST /api/portfolios - name='%s'", portfolio.name)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM portfolios")
        next_order = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO portfolios (name, sort_order, classification, broker) VALUES (?, ?, ?, ?)",
            (portfolio.name.strip(), next_order, portfolio.classification, portfolio.broker)
        )
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success", "id": cursor.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.put("/api/portfolios/reorder")
def reorder_portfolios(payload: PortfoliosReorder):
    logger.info("PUT /api/portfolios/reorder - %d portfolios", len(payload.order))
    conn = get_connection()
    try:
        cursor = conn.cursor()
        for idx, pid in enumerate(payload.order):
            cursor.execute("UPDATE portfolios SET sort_order = ? WHERE id = ?", (idx, pid))
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.put("/api/portfolios/{id}")
def update_portfolio(id: int, portfolio: PortfolioUpdate):
    logger.info("PUT /api/portfolios/%d - name='%s'", id, portfolio.name)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE portfolios SET name = ?, classification = ?, broker = ? WHERE id = ?",
            (portfolio.name.strip(), portfolio.classification, portfolio.broker, id)
        )
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete("/api/portfolios/{id}")
def delete_portfolio(id: int):
    logger.info("DELETE /api/portfolios/%d", id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM portfolios WHERE id = ?", (id,))
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/api/portfolios/{portfolio_id}/shares")
def get_shares_held(portfolio_id: int, ticker: str, date: str):
    """
    Returns the shares quantity of a ticker in a portfolio on a specific date.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        symbol = ticker.strip().upper()
        cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
        row = cursor.fetchone()
        if not row:
            return {"shares": 0.0}
        
        from core.calculations import get_shares_on_date
        shares = get_shares_on_date(portfolio_id, row['id'], date, conn)
        return {"shares": shares}
    finally:
        conn.close()

