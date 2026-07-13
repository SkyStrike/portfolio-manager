import logging
import os
import json
import sqlite3
import datetime
from datetime import timedelta
import yfinance as yf
from core.database import get_connection
from services.price_service import get_yfinance_symbol

logger = logging.getLogger(__name__)

# Silence yfinance logger to suppress verbose 404 errors for ETFs and trusts
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

def get_active_tickers(conn):
    """
    Returns list of active tickers (where shares held > 0).
    Each row contains (id, symbol, exchange, currency)
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.symbol, t.exchange,
               COALESCE(
                   (SELECT tx.currency FROM transactions tx WHERE tx.ticker_id = t.id ORDER BY tx.date DESC LIMIT 1),
                   'USD'
               ) as currency
        FROM tickers t
        JOIN transactions tx ON t.id = tx.ticker_id
        GROUP BY tx.portfolio_id, tx.ticker_id
        HAVING SUM(CASE WHEN tx.action = 'BUY' THEN tx.quantity WHEN tx.action = 'SELL' THEN -tx.quantity ELSE 0 END) > 0.0001
    """)
    return [dict(row) for row in cursor.fetchall()]

def determine_payout_frequency(history_dates):
    """
    Determines payout frequency (12 for Monthly, 4 for Quarterly, 2 for Semi-Annually, 1 for Annually)
    based on historical dates list.
    """
    if len(history_dates) < 2:
        return 4  # Default to Quarterly
    
    # Calculate average gap in days
    gaps = []
    for i in range(1, len(history_dates)):
        diff = (history_dates[i] - history_dates[i-1]).days
        if diff > 0:
            gaps.append(diff)
            
    if not gaps:
        return 4
        
    avg_gap = sum(gaps) / len(gaps)
    if 20 <= avg_gap <= 40:
        return 12  # Monthly
    elif 70 <= avg_gap <= 110:
        return 4   # Quarterly
    elif 150 <= avg_gap <= 210:
        return 2   # Semi-Annually
    elif 300 <= avg_gap <= 390:
        return 1   # Annually
    return 4       # Fallback to Quarterly

def sync_upcoming_dividends(conn, force=False):
    """
    Fetches declared upcoming dividends and generates future estimations for active holdings.
    """
    active_tickers = get_active_tickers(conn)
    now = datetime.datetime.now()
    now_str = now.isoformat()
    
    logger.info("Syncing upcoming dividends for %d active tickers...", len(active_tickers))
    
    for tk in active_tickers:
        ticker_id = tk["id"]
        symbol = tk["symbol"]
        exchange = tk["exchange"]
        currency = tk["currency"]
        
        # Check cache cooldown
        cursor = conn.cursor()
        cursor.execute("""
            SELECT last_updated FROM upcoming_dividends 
            WHERE ticker_id = ? 
            ORDER BY last_updated DESC LIMIT 1
        """, (ticker_id,))
        cache_row = cursor.fetchone()
        
        if cache_row and not force:
            last_upd = datetime.datetime.fromisoformat(cache_row["last_updated"])
            if now - last_upd < timedelta(hours=24):
                # Skipped due to 24 hour cooldown
                continue
                
        logger.debug("Fetching dividend data for %s...", symbol)
        yf_symbol = get_yfinance_symbol(symbol, exchange)
        
        # 1. Fetch yfinance data
        ticker_calendar = None
        historical_divs = []
        last_div_value = None
        
        try:
            yf_ticker = yf.Ticker(yf_symbol)
            
            # Fetch calendar
            try:
                ticker_calendar = yf_ticker.calendar
            except Exception as e:
                logger.debug("No calendar fundamentals for %s: %s", symbol, e)
                
            # Fetch historical dividends
            try:
                history = yf_ticker.dividends
                if history is not None and not history.empty:
                    # Sort oldest to newest
                    history = history.sort_index()
                    historical_divs = [(d.date(), val) for d, val in history.items()]
                    last_div_value = float(history.iloc[-1])
            except Exception as e:
                logger.debug("No dividend history for %s: %s", symbol, e)
                
            # Check info for last dividend value if history was empty
            if last_div_value is None:
                from services.price_service import get_blacklisted_tickers, log_ticker_api_error
                blacklisted = get_blacklisted_tickers(conn, api_type="yfinance_info")
                if yf_symbol not in blacklisted:
                    try:
                        info = yf_ticker.info
                        if not info or not isinstance(info, dict) or ('symbol' not in info and 'longName' not in info):
                            raise ValueError("Invalid ticker or failed to fetch ticker metadata")
                        
                        last_div_value = info.get("lastDividendValue") or info.get("dividendRate")
                        if last_div_value:
                            last_div_value = float(last_div_value)
                        else:
                            last_div_value = 0.0  # Valid ticker, just does not pay dividends
                    except Exception as e:
                        log_ticker_api_error(conn, yf_symbol, api_type="yfinance_info")
                    
        except Exception as e:
            logger.warning("Error fetching yfinance details for %s: %s", symbol, e)
            
        # If no yfinance history, fall back to our local DB paid dividends
        if not historical_divs:
            cursor.execute("""
                SELECT date, amount FROM dividends 
                WHERE ticker_id = ? 
                ORDER BY date ASC
            """, (ticker_id,))
            local_divs = cursor.fetchall()
            for row in local_divs:
                try:
                    dt = datetime.datetime.strptime(row["date"][:10], "%Y-%m-%d").date()
                    historical_divs.append((dt, float(row["amount"])))
                except ValueError:
                    pass
            if historical_divs:
                last_div_value = historical_divs[-1][1]
                
        # 2. Extract Declared upcoming dividend
        declared_ex_date = None
        declared_pay_date = None
        declared_amount = last_div_value
        
        if ticker_calendar and isinstance(ticker_calendar, dict):
            ex_date_val = ticker_calendar.get("Ex-Dividend Date")
            pay_date_val = ticker_calendar.get("Dividend Date")
            
            # yfinance returns datetime.date objects or lists/None
            if isinstance(ex_date_val, datetime.date):
                declared_ex_date = ex_date_val
            elif isinstance(ex_date_val, list) and len(ex_date_val) > 0:
                declared_ex_date = ex_date_val[0]
                
            if isinstance(pay_date_val, datetime.date):
                declared_pay_date = pay_date_val
            elif isinstance(pay_date_val, list) and len(pay_date_val) > 0:
                declared_pay_date = pay_date_val[0]
                
        # If ex_date or pay_date is in the future, save as 'Declared'
        # First, clean existing Estimated/Declared records for this ticker in upcoming_dividends
        with conn:
            conn.execute("DELETE FROM upcoming_dividends WHERE ticker_id = ?", (ticker_id,))
            
        has_future_declared = False
        today = datetime.date.today()
        # If no payment date was declared, project it as ex_date + 10 days
        pay_date = declared_pay_date or (declared_ex_date + timedelta(days=10) if declared_ex_date else None)
        
        if declared_ex_date and declared_amount and (declared_ex_date >= today or (pay_date and pay_date >= today)):
            with conn:
                conn.execute("""
                    INSERT OR REPLACE INTO upcoming_dividends 
                    (ticker_id, ex_date, payment_date, amount, currency, status, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (ticker_id, declared_ex_date.isoformat(), pay_date.isoformat(), 
                      declared_amount, currency, "Declared", now_str))
            has_future_declared = True
            
        # 3. Generate future 'Estimated' dividends for the next 12 months
        if historical_divs:
            hist_dates = [item[0] for item in historical_divs]
            freq = determine_payout_frequency(hist_dates)
            
            # Last payout event date (ex-date)
            last_payout_ex = hist_dates[-1]
            last_payout_pay = declared_pay_date or (last_payout_ex + timedelta(days=10))
            
            # If the latest declared date is even newer, start projections after that
            start_ex = declared_ex_date if declared_ex_date else last_payout_ex
            start_pay = declared_pay_date if declared_pay_date else last_payout_pay
            
            # Offset interval in days
            interval_days = int(365.25 / freq)
            
            # Project up to 12 payouts
            projected_count = 12
            current_ex = start_ex
            current_pay = start_pay
            
            # If the start payout date is in the future, offset backward so the first
            # loop iteration lands exactly on start_ex/start_pay to include it.
            if start_pay >= today:
                current_ex = current_ex - timedelta(days=interval_days)
                current_pay = current_pay - timedelta(days=interval_days)
            
            for _ in range(projected_count):
                current_ex = current_ex + timedelta(days=interval_days)
                current_pay = current_pay + timedelta(days=interval_days)
                
                # Only insert if it is in the future (ex-date or payment_date is future)
                if (current_ex >= today or current_pay >= today) and last_div_value:
                    # Skip if a Declared entry already exists for this exact ex_date
                    cursor.execute("""
                        SELECT id FROM upcoming_dividends 
                        WHERE ticker_id = ? AND ex_date = ?
                    """, (ticker_id, current_ex.isoformat()))
                    if cursor.fetchone():
                        continue
                        
                    with conn:
                        conn.execute("""
                            INSERT OR IGNORE INTO upcoming_dividends 
                            (ticker_id, ex_date, payment_date, amount, currency, status, last_updated)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (ticker_id, current_ex.isoformat(), current_pay.isoformat(), 
                              last_div_value, currency, "Estimated", now_str))
        else:
            # Fallback if no history: write a single fallback update timestamp to avoid infinite retry loops
            with conn:
                conn.execute("""
                    INSERT OR IGNORE INTO upcoming_dividends 
                    (ticker_id, ex_date, payment_date, amount, currency, status, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (ticker_id, "9999-12-31", "9999-12-31", 0.0, currency, "Estimated", now_str))

if __name__ == "__main__":
    # Test run
    conn = get_connection()
    try:
        sync_upcoming_dividends(conn, force=True)
    finally:
        conn.close()
