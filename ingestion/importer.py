import logging
import csv
import os
import sqlite3
from datetime import datetime
from core.database import get_connection

logger = logging.getLogger(__name__)

def clean_friendly_name(name: str) -> str:
    """Removes trailing asterisks and strips whitespace."""
    if not name:
        return ""
    name = name.strip()
    if name.endswith("*"):
        name = name[:-1].strip()
    return name

def get_default_tax_rate(currency: str, country: str, exchange: str = "") -> float:
    """Determines default tax rates: SG = 0%, CAD = 15%, USD = 30%."""
    currency = (currency or "").upper()
    country = (country or "").upper()
    exchange = (exchange or "").strip().upper()
    
    # 1. First check based on exchange code
    if exchange in ("TO", "V"):
        return 0.15
    elif exchange == "SG":
        return 0.0
    elif exchange in ("US", "NYSE", "NASDAQ", "AMEX"):
        return 0.30
        
    # 2. Fall back to currency and country checks
    if "SINGAPORE" in country or currency == "SGD":
        return 0.0
    elif "CANADA" in country or currency == "CAD":
        return 0.15
    elif "UNITED STATES" in country or "US" in country or currency == "USD":
        return 0.30
    return 0.0

def import_portfolio_data(portfolio_name: str, holdings_file_path: str, transactions_file_path: str, conn: sqlite3.Connection):
    """
    Imports holdings and transactions from Snowball exports for a specific portfolio.
    Creates the portfolio if it doesn't exist.
    """
    cursor = conn.cursor()
    
    # 1. Ensure portfolio exists
    cursor.execute("INSERT OR IGNORE INTO portfolios (name) VALUES (?)", (portfolio_name,))
    conn.commit()
    cursor.execute("SELECT id FROM portfolios WHERE name = ?", (portfolio_name,))
    portfolio_id = cursor.fetchone()['id']
    
    imported_tickers = set()
    ticker_symbol_to_id = {}
    
    def resolve_metadata(sym: str, name: str, note: str) -> tuple[str, str]:
        # Resolve underlying
        resolved_underlying = name or sym

        # Resolve category
        p_lower = portfolio_name.lower()
        n_lower = (note or "").lower()
        if "income factory" in p_lower:
            resolved_category = "income"
        elif "long term holdings" in p_lower:
            resolved_category = "growth"
        elif "discord" in p_lower:
            resolved_category = "swing" if "swing" in n_lower else "conviction"
        else:
            resolved_category = "Other"
            
        return resolved_category, resolved_underlying
        
    # Pre-scan transactions file to get exchange mapping for tickers
    symbol_to_exchange = {}
    with open(transactions_file_path, mode='r', encoding='utf-8') as f:
        content = f.read()
        if content.startswith('\ufeff'):
            content = content[1:]
        reader = csv.DictReader(content.splitlines())
        for row in reader:
            sym = row.get("Symbol", "").strip()
            exch = row.get("Exchange", "").strip()
            if sym and exch:
                symbol_to_exchange[sym] = exch

    # 2. Parse Holdings CSV to seed tickers and price info
    # Columns expected: Holding, Holdings' name, Note, Shares, Currency, Share price, Country, Portfolios
    with open(holdings_file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            symbol = row.get("Holding", "").strip()
            if not symbol:
                continue
            
            # Check if this holding belongs to our target portfolio (if the column exists)
            if "Portfolios" in row:
                portfolios_field = row.get("Portfolios", "")
                associated_portfolios = [p.strip().lower() for p in portfolios_field.split(",")]
                if portfolio_name.lower() not in associated_portfolios:
                    continue
                
            friendly_name = clean_friendly_name(row.get("Holdings' name", ""))
            currency = row.get("Currency", "USD").strip().upper()
            country = row.get("Country", "").strip()
            notes = row.get("Note", "").strip()
            share_price = float(row.get("Share price", "0.0") or 0.0)
            
            exchange = symbol_to_exchange.get(symbol, "")
            tax_rate = get_default_tax_rate(currency, country, exchange)
            category, underlying = resolve_metadata(symbol, friendly_name, notes)
            
            # Insert or update ticker
            cursor.execute("""
                INSERT INTO tickers (symbol, friendly_name, tax_rate, notes, exchange, category, underlying)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    friendly_name = COALESCE(excluded.friendly_name, friendly_name),
                    exchange = COALESCE(excluded.exchange, exchange),
                    notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE notes END,
                    category = COALESCE(tickers.category, excluded.category),
                    underlying = COALESCE(tickers.underlying, excluded.underlying),
                    tax_rate = CASE WHEN tickers.tax_rate = 0.0 OR tickers.tax_rate IS NULL THEN excluded.tax_rate ELSE tickers.tax_rate END
            """, (symbol, friendly_name, tax_rate, notes, exchange, category, underlying))
            
            # Retrieve ticker_id
            cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
            ticker_id = cursor.fetchone()['id']
            ticker_symbol_to_id[symbol] = ticker_id
            imported_tickers.add(symbol)
            
            # Seed ticker price (initial reference value)
            cursor.execute("""
                INSERT INTO ticker_prices (ticker_id, price, intraday_current, intraday_prev_close, currency, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker_id) DO UPDATE SET
                    price = excluded.price,
                    intraday_current = excluded.intraday_current,
                    currency = excluded.currency,
                    last_updated = excluded.last_updated
            """, (ticker_id, share_price, share_price, share_price, currency, datetime.now().isoformat()))
            
    # 3. Parse Transactions CSV
    # Columns expected: Event, Date, Symbol, Price, Quantity, Currency, FeeTax, Exchange, Note
    # We sort transactions chronologically before inserting
    transactions_list = []
    
    with open(transactions_file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            symbol = row.get("Symbol", "").strip()
            event = row.get("Event", "").strip().upper()
            if not symbol and event != "FEE":
                continue
                
            date_str = row.get("Date", "").strip()
            price = float(row.get("Price", "0.0") or 0.0)
            quantity = float(row.get("Quantity", "0.0") or 0.0)
            currency = row.get("Currency", "USD").strip().upper()
            fee_tax = float(row.get("FeeTax", "0.0") or 0.0)
            note = row.get("Note", "").strip()
            exchange = row.get("Exchange", "").strip()
            
            transactions_list.append({
                "event": event,
                "date": date_str,
                "symbol": symbol or "PORTFOLIO_FEE",
                "price": price,
                "quantity": quantity,
                "currency": currency,
                "fee_tax": fee_tax,
                "note": note,
                "exchange": exchange
            })
            
    # Sort transactions chronologically
    transactions_list.sort(key=lambda x: x["date"])
    
    # Batch pre-fetch missing historical rates in a range to avoid sequential API calls
    transaction_dates = set()
    currencies_to_fetch = set()
    for tx in transactions_list:
        if tx["currency"] != "SGD":
            currencies_to_fetch.add(tx["currency"])
            dt_part = tx["date"].split()[0]
            transaction_dates.add(dt_part)
            
    if transaction_dates and currencies_to_fetch:
        cursor.execute("SELECT DISTINCT date FROM exchange_rates WHERE date != 'latest'")
        cached_dates = {row['date'] for row in cursor.fetchall()}
        missing_dates = [d for d in transaction_dates if d not in cached_dates]
        
        if missing_dates:
            min_date = min(missing_dates)
            max_date = max(missing_dates)
            logger.info(
                "Batch fetching missing rates for %d dates from %s to %s...",
                len(missing_dates), min_date, max_date
            )
            from services.fetch_exchange_rates import fetch_historical_rates_range
            curr_str = ",".join(sorted(list(currencies_to_fetch)))
            fetch_historical_rates_range(min_date, max_date, curr_str, conn)
            
    # Track stats
    tx_count = 0
    div_count = 0
    
    for tx in transactions_list:
        symbol = tx["symbol"]
        
        # Ensure ticker exists in DB (handles sold-out stocks not in holdings.csv)
        if symbol not in ticker_symbol_to_id:
            cursor.execute("SELECT id, exchange FROM tickers WHERE symbol = ?", (symbol,))
            row_t = cursor.fetchone()
            if not row_t:
                tax_rate = get_default_tax_rate(tx["currency"], "", tx["exchange"])
                category, underlying = resolve_metadata(symbol, symbol, tx["note"])
                cursor.execute("""
                    INSERT INTO tickers (symbol, friendly_name, tax_rate, exchange, category, underlying)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (symbol, symbol, tax_rate, tx["exchange"], category, underlying))
                cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
                ticker_id = cursor.fetchone()['id']
            else:
                ticker_id = row_t['id']
                # If the exchange was empty/none and the transaction has it, update it
                if tx["exchange"] and not row_t['exchange']:
                    tax_rate = get_default_tax_rate(tx["currency"], "", tx["exchange"])
                    cursor.execute("""
                        UPDATE tickers 
                        SET exchange = ?, 
                            tax_rate = CASE WHEN tax_rate = 0.0 THEN ? ELSE tax_rate END
                        WHERE id = ?
                    """, (tx["exchange"], tax_rate, ticker_id))
            ticker_symbol_to_id[symbol] = ticker_id
            
        ticker_id = ticker_symbol_to_id[symbol]
        
        if tx["event"] in ("BUY", "SELL", "SPLIT", "FEE"):
            from services.fetch_exchange_rates import get_historical_exchange_rate
            get_historical_exchange_rate(tx["date"], tx["currency"], conn)
            cursor.execute("""
                INSERT INTO transactions (portfolio_id, ticker_id, date, action, price, quantity, currency, commission, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (portfolio_id, ticker_id, tx["date"], tx["event"], tx["price"], tx["quantity"], tx["currency"], tx["fee_tax"], tx["note"]))
            tx_count += 1
            
        elif tx["event"] in ("DIVIDEND", "OTHER_INCOME"):
            # OTHER_INCOME events (like Return of Capital or Option Premium) are treated as dividend cashflow distributions
            clean_date = tx["date"].strip().split()[0].split('T')[0][:10] if tx["date"] else ""
            from services.fetch_exchange_rates import get_historical_exchange_rate
            get_historical_exchange_rate(clean_date, tx["currency"], conn)
            note_text = f"{tx['event']}: {tx['note']}" if tx['note'] else tx['event']
            from core.calculations import get_shares_on_date
            qty = get_shares_on_date(portfolio_id, ticker_id, clean_date, conn)
            cursor.execute("""
                INSERT INTO dividends (portfolio_id, ticker_id, date, amount, currency, tax, notes, qty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (portfolio_id, ticker_id, clean_date, tx["quantity"], tx["currency"], tx["fee_tax"], note_text, qty))
            div_count += 1
            
    conn.commit()
    logger.info("Imported portfolio '%s': %d transactions and %d dividends.", portfolio_name, tx_count, div_count)
    return tx_count, div_count

if __name__ == "__main__":
    # Test script if executed directly
    conn = get_connection()
    try:
        # Example test import
        import_portfolio_data("Discord Trades", "import/snowball-holdings.csv", "import/snowball-transactions.csv", conn)
    finally:
        conn.close()
