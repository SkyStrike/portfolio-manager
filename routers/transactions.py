import logging
from fastapi import APIRouter, HTTPException
from core.database import get_connection
from core.calculations import calculate_holdings
from core.schemas import TransactionCreate
from core.cache import rebuild_dashboard_sync
from services.fetch_exchange_rates import get_historical_exchange_rate

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/transactions")
def list_transactions(portfolio_id: int | None = None, symbol: str | None = None):
    logger.info("GET /api/transactions (portfolio_id=%s, symbol=%s)", portfolio_id, symbol)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT t.id, t.portfolio_id, t.ticker_id, t.date, t.action, t.price, t.quantity, 
                   t.currency, t.commission, t.cost_basis_after, t.realized_pl, t.notes,
                   tk.symbol, tk.friendly_name, tk.exchange, p.name as portfolio_name
            FROM transactions t
            JOIN tickers tk ON t.ticker_id = tk.id
            JOIN portfolios p ON t.portfolio_id = p.id
            WHERE 1=1
        """
        params = []
        if portfolio_id is not None:
            query += " AND t.portfolio_id = ?"
            params.append(portfolio_id)
        if symbol is not None:
            query += " AND tk.symbol = ?"
            params.append(symbol)
        query += " ORDER BY t.date DESC, t.id DESC"
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@router.post("/api/transactions")
def create_transaction(tx: TransactionCreate):
    logger.info("POST /api/transactions - ticker=%s, action=%s, date=%s, qty=%s, price=%s",
                tx.ticker, tx.action, tx.date, tx.quantity, tx.price)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        symbol = tx.ticker.strip().upper()
        cursor.execute("""
            SELECT t.id, tp.currency, t.exchange 
            FROM tickers t 
            LEFT JOIN ticker_prices tp ON t.id = tp.ticker_id 
            WHERE t.symbol = ?
        """, (symbol,))
        ticker_row = cursor.fetchone()
        if not ticker_row:
            # Create ticker on the fly
            logger.info("Ticker '%s' not found — creating automatically.", symbol)
            exchange = (tx.exchange or "").strip().upper()
            if exchange == "US":
                exchange = ""
            elif not exchange:
                if tx.currency == "CAD":
                    exchange = "TO"
                elif tx.currency == "SGD":
                    exchange = "SG"
                else:
                    exchange = ""
                    
            cursor.execute("INSERT INTO tickers (symbol, friendly_name, tax_rate, exchange) VALUES (?, ?, ?, ?)", (symbol, symbol, 0.30 if tx.currency == "USD" else (0.15 if tx.currency == "CAD" else 0.0), exchange))
            ticker_id = cursor.lastrowid
            # Seed ticker price initially
            cursor.execute("INSERT OR IGNORE INTO ticker_prices (ticker_id, price, prev_close, currency, last_updated) VALUES (?, ?, ?, ?, datetime('now'))", (ticker_id, tx.price, tx.price, tx.currency))
        else:
            ticker_id = ticker_row['id']
            if tx.exchange and not ticker_row['exchange']:
                cursor.execute("UPDATE tickers SET exchange = ? WHERE id = ?", (tx.exchange.strip().upper(), ticker_id))
            
        get_historical_exchange_rate(tx.date, tx.currency, conn)
        
        cursor.execute("""
            INSERT INTO transactions (portfolio_id, ticker_id, date, action, price, quantity, currency, commission, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tx.portfolio_id, ticker_id, tx.date, tx.action.upper(), tx.price, tx.quantity, tx.currency, tx.commission, tx.notes))
        
        # Keep ticker_prices default currency in sync with the transaction currency
        cursor.execute("UPDATE ticker_prices SET currency = ? WHERE ticker_id = ?", (tx.currency, ticker_id))
        
        # Trigger running cost basis calculation
        calculate_holdings(tx.portfolio_id, conn)
        conn.commit()
        rebuild_dashboard_sync(conn)
        logger.info("Transaction created (id=%d) and dashboard rebuilt.", cursor.lastrowid)
        return {"status": "success", "id": cursor.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
 
@router.put("/api/transactions/{id}")
def update_transaction(id: int, tx: TransactionCreate):
    logger.info("PUT /api/transactions/%d - ticker=%s, action=%s, date=%s", id, tx.ticker, tx.action, tx.date)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Find symbol ticker_id
        symbol = tx.ticker.strip().upper()
        cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
        ticker_row = cursor.fetchone()
        if not ticker_row:
            raise HTTPException(status_code=404, detail="Ticker not found.")
        ticker_id = ticker_row['id']
        
        get_historical_exchange_rate(tx.date, tx.currency, conn)
        
        cursor.execute("""
            UPDATE transactions
            SET portfolio_id = ?, ticker_id = ?, date = ?, action = ?, price = ?, quantity = ?, currency = ?, commission = ?, notes = ?
            WHERE id = ?
        """, (tx.portfolio_id, ticker_id, tx.date, tx.action.upper(), tx.price, tx.quantity, tx.currency, tx.commission, tx.notes, id))
        
        # Keep ticker_prices default currency in sync with the transaction currency
        cursor.execute("UPDATE ticker_prices SET currency = ? WHERE ticker_id = ?", (tx.currency, ticker_id))
        
        # Recalculate holdings for the old/new portfolio
        calculate_holdings(tx.portfolio_id, conn)
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete("/api/transactions/{id}")
def delete_transaction(id: int):
    logger.info("DELETE /api/transactions/%d", id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Find portfolio_id first to recalculate cost basis
        cursor.execute("SELECT portfolio_id FROM transactions WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transaction not found.")
        portfolio_id = row['portfolio_id']
        
        cursor.execute("DELETE FROM transactions WHERE id = ?", (id,))
        calculate_holdings(portfolio_id, conn)
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    finally:
        conn.close()
