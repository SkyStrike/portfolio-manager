import logging
import requests
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

BASE_URL = "https://api.frankfurter.app"
FROM_CURRENCY = "SGD"
TO_CURRENCIES = "USD,CAD"

# Retrieve configuration from env
MAX_POLL_HOURS = int(os.getenv("exchange_rates_max_poll_hours", 6))
DECIMALS = int(os.getenv("exchange_rates_decimals", 4))

def get_latest_exchange_rates():
    """Fetches live rates from the API and transforms them into the expected format."""
    try:
        response = requests.get(
            f"{BASE_URL}/latest?from={FROM_CURRENCY}&to={TO_CURRENCIES}", 
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if not data or "rates" not in data:
            return None

        # API returns SGD as base, so rates are 1 SGD = X USD/CAD.
        # The script calculates 1 USD = Y SGD by taking the reciprocal.
        return {
            "USD": round(1 / data["rates"]["USD"], DECIMALS),
            "CAD": round(1 / data["rates"]["CAD"], DECIMALS),
            FROM_CURRENCY: 1.0
        }
    except Exception as e:
        logger.error("Error fetching exchange rates: %s", e)
        return None

def _get_db_connection():
    from core.database import get_connection
    return get_connection()

def get_exchange_rates():
    """
    Main entry point. Returns cached rates if they are fresh in the database, 
    otherwise attempts to fetch live rates and updates the database.
    """
    rates = {}
    last_updated_str = None
    
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT currency, rate, last_updated FROM exchange_rates WHERE date = 'latest'")
        rows = cursor.fetchall()
        for row in rows:
            rates[row['currency']] = row['rate']
            last_updated_str = row['last_updated']
        conn.close()
    except Exception as e:
        logger.error("Error reading exchange rates from DB: %s", e)
        
    # Check if cache is fresh
    is_fresh = False
    if rates and last_updated_str:
        try:
            last_updated = datetime.fromisoformat(last_updated_str)
            if datetime.now() - last_updated < timedelta(hours=MAX_POLL_HOURS):
                is_fresh = True
        except ValueError:
            pass
            
    if is_fresh:
        rates[FROM_CURRENCY] = 1.0
        return rates

    # Fetch new data
    new_rates = get_latest_exchange_rates()
    if new_rates:
        now_str = datetime.now().isoformat()
        try:
            conn = _get_db_connection()
            with conn:
                for currency, rate in new_rates.items():
                    conn.execute("""
                        INSERT INTO exchange_rates (date, currency, rate, last_updated)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(date, currency) DO UPDATE SET rate=excluded.rate, last_updated=excluded.last_updated
                    """, ("latest", currency, rate, now_str))
            conn.close()
            return new_rates
        except Exception as e:
            logger.error("Error saving exchange rates to DB: %s", e)
            return new_rates

    # Fallback to stale database cache if API call fails
    if rates:
        logger.warning("API fetch failed. Using stale database exchange rate cache.")
        rates[FROM_CURRENCY] = 1.0
        return rates

    return {FROM_CURRENCY: 1.0}

_historical_db_cache = None

def get_historical_exchange_rate(date_str: str, currency: str, conn=None) -> float:
    """
    Returns the historical exchange rate (1 native currency = X SGD) for the given date.
    Uses the exchange_rates database table for caching, pre-loading into memory to prevent database query overhead.
    """
    if not date_str or currency == "SGD":
        return 1.0
        
    # Extract YYYY-MM-DD
    date_part = date_str.split()[0]
    cache_key = (date_part, currency)
    
    global _historical_db_cache
    
    # 1. Check in-memory cache first
    if _historical_db_cache is not None:
        if cache_key in _historical_db_cache:
            return _historical_db_cache[cache_key]
    else:
        # Lazy load the cache from DB
        _historical_db_cache = {}
        local_conn = None
        if conn is None:
            try:
                local_conn = _get_db_connection()
                db_conn = local_conn
            except Exception as e:
                logger.error("Error connecting to DB: %s", e)
                db_conn = None
        else:
            db_conn = conn
            
        if db_conn:
            try:
                cursor = db_conn.cursor()
                cursor.execute("SELECT date, currency, rate FROM exchange_rates WHERE date != 'latest'")
                rows = cursor.fetchall()
                for row in rows:
                    _historical_db_cache[(row['date'], row['currency'])] = row['rate']
            except Exception as e:
                logger.error("Error pre-loading exchange rates: %s", e)
                
        if local_conn:
            local_conn.close()
            
        if cache_key in _historical_db_cache:
            return _historical_db_cache[cache_key]
            
    # Try to find the closest preceding date in cache (up to 4 days) for weekends/holidays
    if _historical_db_cache is not None:
        matching_dates = [d for (d, c) in _historical_db_cache.keys() if c == currency and d <= date_part]
        if matching_dates:
            closest_date = max(matching_dates)
            from datetime import date
            try:
                d1 = date.fromisoformat(date_part)
                d2 = date.fromisoformat(closest_date)
                if (d1 - d2).days <= 4:
                    return _historical_db_cache[(closest_date, currency)]
            except ValueError:
                pass
        
    # Fetch from API if not cached
    rate = None
    try:
        response = requests.get(
            f"{BASE_URL}/{date_part}?from={FROM_CURRENCY}&to={currency}",
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if "rates" in data and currency in data["rates"]:
                # 1 SGD = X USD/CAD => 1 USD/CAD = 1/X SGD
                rate = round(1.0 / data["rates"][currency], 4)
                
                # Write to the database.
                # If the caller already holds a connection (and likely an open write
                # transaction), reuse it to avoid "database is locked" from a competing
                # second write connection. Only open a fresh connection when none exists.
                write_conn = None
                close_write_conn = False
                try:
                    if conn is not None:
                        write_conn = conn
                    else:
                        write_conn = _get_db_connection()
                        close_write_conn = True
                    write_conn.execute("""
                        INSERT INTO exchange_rates (date, currency, rate, last_updated)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(date, currency) DO UPDATE SET rate=excluded.rate, last_updated=excluded.last_updated
                    """, (date_part, currency, rate, datetime.now().isoformat()))
                    if close_write_conn:
                        write_conn.commit()
                except Exception as db_err:
                    logger.error("Error saving historical rate to DB: %s", db_err)
                finally:
                    if close_write_conn and write_conn:
                        write_conn.close()
                        
                # Update in-memory cache
                _historical_db_cache[cache_key] = rate
    except Exception as e:
        logger.error("Error fetching historical rate for %s %s: %s", date_part, currency, e)
        
    if rate is not None:
        return rate
        
    # Fallback to current rates
    current_rates = get_exchange_rates()
    return current_rates.get(currency, 1.0)

def fetch_historical_rates_range(start_date_str: str, end_date_str: str, target_currencies: str = "USD,CAD", conn=None) -> bool:
    """
    Fetches historical exchange rates from the Frankfurter API for a range of dates
    and writes them directly to the database.
    
    start_date_str: start date in format YYYY-MM-DD (or full date string containing YYYY-MM-DD)
    end_date_str: end date in format YYYY-MM-DD (or full date string containing YYYY-MM-DD)
    target_currencies: comma-separated list of currencies to fetch (e.g., "USD,CAD")
    """
    start_date = start_date_str.split()[0]
    end_date = end_date_str.split()[0]
    
    try:
        url = f"{BASE_URL}/{start_date}..{end_date}?from={FROM_CURRENCY}&to={target_currencies}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            logger.warning("Frankfurter API returned status %d for range %s..%s", response.status_code, start_date, end_date)
            return False

        data = response.json()
        if not data or "rates" not in data:
            logger.warning("No rates found in response for range %s..%s", start_date, end_date)
            return False
            
        rates_by_date = data["rates"]
        write_conn = conn
        close_conn = False
        if write_conn is None:
            write_conn = _get_db_connection()
            close_conn = True
            
        inserted_count = 0
        try:
            with write_conn:
                for date_key, currencies in rates_by_date.items():
                    for curr, value in currencies.items():
                        # 1 SGD = X USD/CAD => 1 USD/CAD = 1/X SGD
                        rate = round(1.0 / value, 4)
                        write_conn.execute("""
                            INSERT INTO exchange_rates (date, currency, rate, last_updated)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(date, currency) DO UPDATE SET rate=excluded.rate, last_updated=excluded.last_updated
                        """, (date_key, curr, rate, datetime.now().isoformat()))
                        
                        # Also update in-memory cache if it is initialized
                        global _historical_db_cache
                        if _historical_db_cache is not None:
                            _historical_db_cache[(date_key, curr)] = rate
                        inserted_count += 1
            logger.info("Fetched and cached %d historical exchange rates for range %s..%s", inserted_count, start_date, end_date)
            return True
        finally:
            if close_conn:
                write_conn.close()
    except Exception as e:
        logger.error("Error fetching historical exchange rates for range %s..%s: %s", start_date, end_date, e)
        return False

if __name__ == "__main__":
    rates = get_exchange_rates()
    logger.info("Latest rates: %s", rates)
    historical = get_historical_exchange_rate("2025-06-05", "USD")
    logger.info("Historical rate for 2025-06-05 USD: %s", historical)
    logger.info("Testing date range fetch 2026-01-01 to 2026-01-05:")
    fetch_historical_rates_range("2026-01-01", "2026-01-05", "USD,CAD")

