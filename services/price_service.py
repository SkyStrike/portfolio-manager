import logging
import sqlite3
from datetime import datetime, timedelta, timezone, time
import yfinance as yf
import pytz
import pandas as pd

logger = logging.getLogger(__name__)

# ==============================================================================
# TICKER PRICES SCHEMA DOCUMENTATION (Option 1)
# ==============================================================================
# The `ticker_prices` table contains several price/close columns to correctly
# support both Intraday and Closing price modes without daily change collisions:
#
# 1. `intraday_price`     -> Current active price (e.g. Wednesday Live).
#                            Maps to 'price' for backward compatibility.
# 2. `prev_close`         -> The base price for Intraday mode daily change
#                            calculations: (intraday_price - prev_close).
#                            Holds yesterday's close (e.g. Tuesday Close).
# 3. `closing_price`      -> The price of the latest completed session
#                            (e.g. Tuesday Close during Wednesday trading).
# 4. `prev_closing_price` -> The base price for Closing mode daily change
#                            calculations: (closing_price - prev_closing_price).
#                            Holds day-before-yesterday's close (e.g. Monday Close).
# ==============================================================================

# Silence yfinance logger to suppress verbose 404 errors for ETFs and trusts
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# Cooldown timer to prevent abuse
_last_refresh_time = None
REFRESH_COOLDOWN = timedelta(minutes=10)

def get_now_utc() -> datetime:
    """Returns the current naive UTC datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def get_yfinance_symbol(symbol: str, exchange: str) -> str:
    """Appends appropriate suffix to tickers for Yahoo Finance lookup."""
    symbol = symbol.strip()
    exchange = (exchange or "").strip().upper()
    
    if exchange == "SG":
        return f"{symbol}.SI"
    elif exchange == "TO" or exchange == "TSE":
        return f"{symbol}.TO"
    elif exchange == "V":
        return f"{symbol}.V"
    elif exchange == "NE" or exchange == "NEO":
        return f"{symbol}.NE"
    return symbol

def is_exchange_in_session(exchange: str) -> bool:
    """
    Checks if the local exchange time is within active weekday trading hours.
    US/Canada: 9:30 AM - 4:00 PM EST (Monday - Friday)
    Singapore: 9:00 AM - 5:00 PM SGT (Monday - Friday)
    """
    import pytz
    from datetime import datetime, time
    
    exchange_upper = (exchange or "").strip().upper()
    if exchange_upper == "SG":
        tz = pytz.timezone('Asia/Singapore')
        start_time = time(9, 0)
        end_time = time(17, 0)
    elif exchange_upper in ["TO", "TSE", "V", "TSX", "NEO", "NE", "CSE"]:
        tz = pytz.timezone('America/Toronto')
        start_time = time(9, 30)
        end_time = time(16, 0)
    else:
        # Default to US
        tz = pytz.timezone('America/New_York')
        start_time = time(9, 30)
        end_time = time(16, 0)

    now_tz = datetime.now(tz)
    # Check weekday (0 = Monday, ..., 4 = Friday)
    if now_tz.weekday() > 4:
        return False
        
    current_time = now_tz.time()
    return start_time <= current_time <= end_time

def is_price_fresh_after_close(last_updated: datetime, exchange: str) -> bool:
    """
    Checks if the last_updated naive timestamp (assumed SGT/local server time) is after
    the most recent completed trading session close of the exchange.
    """
    import pytz
    from datetime import time, timedelta
    
    exchange_upper = (exchange or "").strip().upper()
    if exchange_upper == "SG":
        tz = pytz.timezone('Asia/Singapore')
        session_close_time = time(17, 0)
    elif exchange_upper in ["TO", "TSE", "V", "TSX", "NEO", "NE", "CSE"]:
        tz = pytz.timezone('America/Toronto')
        session_close_time = time(16, 0)
    else:
        tz = pytz.timezone('America/New_York')
        session_close_time = time(16, 0)

    # Localize UTC server time and convert to exchange local time
    local_tz = pytz.utc
    try:
        last_updated_localized = local_tz.localize(last_updated).astimezone(tz)
    except Exception:
        # Fallback if already timezone aware
        last_updated_localized = last_updated.astimezone(tz)
        
    now_tz = datetime.now(tz)
    
    # Calculate the most recent close day
    check_date = now_tz.date()
    while check_date.weekday() > 4: # Skip weekend
        check_date -= timedelta(days=1)
        
    most_recent_close = tz.localize(datetime.combine(check_date, session_close_time))
    
    # If today is a weekday but we are currently before market close,
    # the last completed close was on the previous weekday
    if check_date == now_tz.date() and now_tz < most_recent_close:
        check_date -= timedelta(days=1)
        while check_date.weekday() > 4:
            check_date -= timedelta(days=1)
        most_recent_close = tz.localize(datetime.combine(check_date, session_close_time))
        
    return last_updated_localized >= most_recent_close

def log_ticker_api_error(conn: sqlite3.Connection, ticker: str, api_type: str = "yfinance_info"):
    """Increments the error count for a ticker in the database."""
    try:
        cursor = conn.cursor()
        now_str = get_now_utc().isoformat()
        cursor.execute("""
            INSERT INTO ticker_api_errors (ticker, api_type, error_count, last_error_time)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(ticker, api_type) DO UPDATE SET
                error_count = error_count + 1,
                last_error_time = excluded.last_error_time
        """, (ticker, api_type, now_str))
        conn.commit()
    except Exception as e:
        logger.warning("Failed to log ticker API error: %s", e)

def get_blacklisted_tickers(conn: sqlite3.Connection, api_type: str = "yfinance_info", max_errors: int = 3) -> set:
    """Returns a set of tickers that have consistently thrown API errors for a specific api_type."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ticker_api_errors'")
        if not cursor.fetchone():
            return set()
        cursor.execute("SELECT ticker FROM ticker_api_errors WHERE api_type = ? AND error_count >= ?", (api_type, max_errors))
        rows = cursor.fetchall()
        return {r['ticker'] for r in rows}
    except Exception as e:
        logger.warning("Failed to query blacklisted tickers: %s", e)
        return set()

def update_prices(conn: sqlite3.Connection = None, force: bool = False, cache_minutes: int = 60) -> dict:
    """
    Fetches latest prices in a single batch from yfinance and caches them in the DB.
    Only queries tickers whose cached prices are older than `cache_minutes` unless `force` is True.
    """
    close_on_exit = False
    if conn is None:
        from core.database import get_connection
        conn = get_connection()
        close_on_exit = True

    try:
        cursor = conn.cursor()
        
        # 1. Query active tickers in the database (tickers with shares > 0 across portfolios)
        cursor.execute("""
            SELECT ticker_id,
                   SUM(CASE
                       WHEN action IN ('BUY', 'SPLIT') THEN quantity
                       WHEN action = 'SELL'            THEN -quantity
                       ELSE 0
                   END) AS net_qty
            FROM transactions
            GROUP BY ticker_id
            HAVING net_qty > 0.0001
        """)
        active_ticker_ids = {row['ticker_id'] for row in cursor.fetchall()}
                    
        if not active_ticker_ids:
            return {"status": "success", "message": "No active holdings in database. No price fetch needed."}
            
        placeholders = ','.join('?' for _ in active_ticker_ids)
        cursor.execute(f"SELECT id, symbol, exchange FROM tickers WHERE id IN ({placeholders})", tuple(active_ticker_ids))
        tickers = cursor.fetchall()
            
        # Create symbol lookup mappings
        ticker_id_map = {t['symbol']: t['id'] for t in tickers}
        db_symbols = [t['symbol'] for t in tickers]
        
        # Check last updated times in ticker_prices
        cursor.execute("SELECT ticker_id, last_updated FROM ticker_prices")
        price_records = {r['ticker_id']: r['last_updated'] for r in price_records_rows} if (price_records_rows := cursor.fetchall()) else {}
        
        tickers_to_fetch = []
        
        for t in tickers:
            ticker_id = t['id']
            symbol = t['symbol']
            
            # Determine if ticker needs update
            needs_update = False
            if ticker_id not in price_records:
                needs_update = True
            else:
                try:
                    last_updated = datetime.fromisoformat(price_records[ticker_id])
                    
                    if is_exchange_in_session(t['exchange']):
                        # If the exchange is in session, refresh if force=True OR cache expired
                        if force:
                            needs_update = True
                        elif get_now_utc() - last_updated > timedelta(minutes=cache_minutes):
                            needs_update = True
                    else:
                        # Exchange is closed. Only refresh if the DB price is not fresh after the last close
                        if not is_price_fresh_after_close(last_updated, t['exchange']):
                            needs_update = True
                except (ValueError, TypeError):
                    needs_update = True
                    
            if needs_update:
                tickers_to_fetch.append(t)
                
        if not tickers_to_fetch:
            return {"status": "success", "message": "All prices are fresh. No fetch needed."}
            
        # Map database symbol to yfinance query symbol
        yf_to_db = {}
        yf_to_exchange = {}
        yf_symbols = []
        for t in tickers_to_fetch:
            yf_sym = get_yfinance_symbol(t['symbol'], t['exchange'])
            yf_symbols.append(yf_sym)
            yf_to_db[yf_sym] = t['symbol']
            yf_to_exchange[yf_sym] = t['exchange']
            
        logger.info("Fetching updates from yfinance for %d tickers...", len(yf_symbols))
        
        # Fetch 5 days of history in batch (5d ensures we get previous closes even over weekends)
        df = yf.download(yf_symbols, period="5d", threads=False, progress=False)
        
        # Check if download succeeded and df is not empty
        if df.empty or 'Close' not in df:
            return {"status": "error", "message": "Empty response from yfinance"}
            
        import pandas as pd
        
        # Detect tickers completely absent from the batch response (not NaN rows, but missing entirely)
        if isinstance(df.columns, pd.MultiIndex):
            returned_in_batch = set(df['Close'].columns.tolist())
        else:
            returned_in_batch = set(yf_symbols) if not df.empty else set()
            
        failed_symbols = []
        absent_symbols = set(yf_symbols) - returned_in_batch
        if absent_symbols:
            logger.warning("[price] Tickers absent from batch response (possible rate-limit): %s", absent_symbols)
            failed_symbols.extend(list(absent_symbols))

        # Identify tickers that failed to return a valid Close (NaN or missing)
        # or have any row with volume > 0 and NaN Close
        for yf_sym in yf_symbols:
            close_series = pd.Series(dtype=float)
            vol_series = pd.Series(dtype=float)
            
            if 'Close' in df:
                close_col = df['Close']
                if isinstance(close_col, pd.Series):
                    close_series = close_col
                elif yf_sym in close_col:
                    close_series = close_col[yf_sym]
                    
            if 'Volume' in df:
                vol_col = df['Volume']
                if isinstance(vol_col, pd.Series):
                    vol_series = vol_col
                elif yf_sym in vol_col:
                    vol_series = vol_col[yf_sym]
            
            # Check if the latest trading day (Volume > 0) has a NaN Close price
            has_nan_latest_close = False
            if not close_series.empty and not vol_series.empty:
                combined = pd.DataFrame({'Close': close_series, 'Volume': vol_series})
                trading_days = combined[combined['Volume'] > 0]
                if not trading_days.empty:
                    latest_trading_day = trading_days.iloc[-1]
                    if pd.isna(latest_trading_day['Close']):
                        has_nan_latest_close = True
                
            is_all_nan_close = close_series.dropna().empty
            
            if is_all_nan_close or has_nan_latest_close:
                failed_symbols.append(yf_sym)
                
        # Retry failed symbols with period="1d"
        df_retry = None
        if failed_symbols:
            logger.info("Retrying %d failed tickers with period='1d': %s", len(failed_symbols), failed_symbols)
            try:
                df_retry = yf.download(failed_symbols, period="1d", interval="1d", threads=False, progress=False)
                if df_retry.empty or 'Close' not in df_retry:
                    df_retry = None
            except Exception as retry_ex:
                logger.warning("yfinance retry failed: %s", retry_ex)
            
        # Determine Global Last Trading Date across all fetched data (main and retry)
        all_dates = []
        for dset in [df, df_retry]:
            if dset is not None and not dset.empty and 'Close' in dset:
                close_data = dset['Close']
                if isinstance(close_data, pd.DataFrame):
                    valid_dates = close_data.dropna(how='all').index
                else:
                    valid_dates = close_data.dropna().index
                if len(valid_dates) > 0:
                    all_dates.extend(valid_dates)
                    
        global_last_date_str = None
        if all_dates:
            global_max = max(all_dates)
            if hasattr(global_max, "strftime"):
                global_last_date_str = global_max.strftime("%Y-%m-%d")
            else:
                global_last_date_str = str(global_max).split()[0]

        # Parallel fetch of full info metadata to get correct previousClose and lastPrice (adjusted for corporate actions/dividends)
        info_metadata = {}
        from concurrent.futures import ThreadPoolExecutor
        
        # Get blacklisted tickers to skip fetching their info via Ticker.info (avoids repetitive 404 errors)
        blacklisted_tickers = get_blacklisted_tickers(conn)
        
        # Skip fetch_info calls when all markets are closed (batch closed prices are authoritative)
        any_market_open = any(is_exchange_in_session(yf_to_exchange.get(sym, "")) for sym in yf_symbols)
        if any_market_open:
            symbols_to_info = [sym for sym in yf_symbols if sym not in blacklisted_tickers]
        else:
            logger.info("[price] All exchanges closed — skipping fetch_info, using batch close prices.")
            symbols_to_info = []
        
        def fetch_info(sym):
            logger.debug("Fetching info: %s", sym)
            try:
                t = yf.Ticker(sym)
                # First try fast_info to avoid HTTP 404 fundamentals queries
                fast_info = getattr(t, "fast_info", {})
                prev_close = fast_info.get('regularMarketPreviousClose') or fast_info.get('previousClose')
                last_price = fast_info.get('lastPrice') or fast_info.get('regularMarketPrice')
                
                # If fast_info fields are missing/None, fallback to standard Ticker.info lookup
                if prev_close is None or last_price is None:
                    info = t.info
                    prev_close = prev_close or info.get('regularMarketPreviousClose') or info.get('previousClose')
                    last_price = last_price or info.get('regularMarketPrice') or info.get('lastPrice') or info.get('ask') or info.get('bid')
                
                if prev_close is None or last_price is None:
                    raise ValueError(f"No price data found in yfinance metadata for {sym}")
                
                logger.debug("Fetched info OK: %s", sym)
                return sym, {
                    'previousClose': prev_close,
                    'lastPrice': last_price
                }
            except Exception as e:
                logger.warning("Failed to fetch info for %s: %s", sym, e)
                # Log API error to SQLite database
                try:
                    from core.database import get_connection
                    err_conn = get_connection()
                    try:
                        log_ticker_api_error(err_conn, sym)
                    finally:
                        err_conn.close()
                except Exception:
                    pass
                return sym, None

        if symbols_to_info:
            logger.info(
                "Fetching info metadata in parallel for %d of %d symbols: %s",
                len(symbols_to_info), len(yf_symbols), ", ".join(symbols_to_info)
            )
            # Load dynamic workers limit from config
            from services.rebuild_dashboard import load_config
            config = load_config()
            max_workers = config.get("finance", {}).get("max_workers", 30)
            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    info_results = list(executor.map(fetch_info, symbols_to_info))
                    for sym, info in info_results:
                        if info:
                            info_metadata[sym] = info
            except Exception as e:
                logger.error("Failed to fetch info metadata: %s", e)
        else:
            logger.info("No symbols to fetch info metadata for (all either blacklisted or skipped).")

        updated_records = []
        now_str = get_now_utc().isoformat()
        
        for yf_sym in yf_symbols:
            db_symbol = yf_to_db[yf_sym]
            ticker_id = ticker_id_map[db_symbol]
            exchange = yf_to_exchange.get(yf_sym, "")
            
            try:
                # 1. Try to extract Series from main df
                series = pd.Series(dtype=float)
                if 'Close' in df:
                    close_col = df['Close']
                    if isinstance(close_col, pd.Series):
                        series = close_col.dropna()
                    elif yf_sym in close_col:
                        series = close_col[yf_sym].dropna()
                
                # Check if this ticker was retried
                is_retried = (yf_sym in failed_symbols)
                
                # Try to extract Series from df_retry if it was retried
                series_retry = pd.Series(dtype=float)
                if is_retried and df_retry is not None and 'Close' in df_retry:
                    close_col_retry = df_retry['Close']
                    if isinstance(close_col_retry, pd.Series):
                        series_retry = close_col_retry.dropna()
                    elif yf_sym in close_col_retry:
                        series_retry = close_col_retry[yf_sym].dropna()
                
                # Determine standard fields based on which datasets have data
                has_data = False
                if not series_retry.empty:
                    # Use retry data for the latest price (e.g. today's 19.96)
                    intraday_price = float(series_retry.iloc[-1])
                    # For prev_close, use the latest valid price from df, fallback to retry's second-to-last or same price
                    if not series.empty:
                        prev_close = float(series.iloc[-1])
                    else:
                        prev_close = float(series_retry.iloc[-2]) if len(series_retry) >= 2 else intraday_price
                    last_date = series_retry.index[-1]
                    has_data = True
                elif not series.empty:
                    # Normal flow using main df
                    intraday_price = float(series.iloc[-1])
                    prev_close = float(series.iloc[-2]) if len(series) >= 2 else intraday_price
                    last_date = series.index[-1]
                    has_data = True
                
                if has_data:
                    # 1. Zero/negative price guard
                    if intraday_price <= 0:
                        logger.warning("[price] Zero/negative price for %s (%s): %.4f — skipping update", db_symbol, yf_sym, intraday_price)
                        has_data = False
                        
                if has_data:
                    # Determine latest closing price vs intraday price
                    if hasattr(last_date, "strftime"):
                        last_date_str = last_date.strftime("%Y-%m-%d")
                    else:
                        last_date_str = str(last_date).split()[0]
                    
                    # Override with full info metadata if available and valid
                    meta = info_metadata.get(yf_sym)
                    if meta:
                        if meta.get('lastPrice') is not None and not pd.isna(meta['lastPrice']) and float(meta['lastPrice']) > 0:
                            intraday_price = float(meta['lastPrice'])
                        if meta.get('previousClose') is not None and not pd.isna(meta['previousClose']) and float(meta['previousClose']) > 0:
                            prev_close = float(meta['previousClose'])
                    
                    # 2. Staleness guard
                    from datetime import date as _date
                    last_date_dt = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                    days_stale = (datetime.utcnow().date() - last_date_dt).days
                    local_weekday = True
                    try:
                        # Safely resolve wrapped helper check if exists
                        local_weekday = is_exchange_in_session(exchange)
                    except Exception:
                        pass
                    if days_stale > 5 and local_weekday:
                        logger.warning("[price] Stale price for %s: last date %s is %d days old on weekday — keeping existing", db_symbol, last_date_str, days_stale)
                        has_data = False

                if has_data:
                    # 3. Ratio bounds guard (extreme price move check)
                    cursor.execute("SELECT intraday_price FROM ticker_prices WHERE ticker_id = ?", (ticker_id,))
                    existing_row = cursor.fetchone()
                    if existing_row and existing_row['intraday_price']:
                        existing = float(existing_row['intraday_price'])
                        if existing > 0:
                            ratio = intraday_price / existing
                            if ratio > 5.0 or ratio < 0.20:
                                logger.warning("[price] Suspicious price move for %s: %.4f -> %.4f (%.2fx) — ignoring", db_symbol, existing, intraday_price, ratio)
                                try:
                                    log_ticker_api_error(conn, yf_sym)
                                except Exception:
                                    pass
                                has_data = False

                if has_data:
                    # --- Holiday and Midnight Reset Logic ---
                    # Resolve exchange timezone for local date/weekday checking
                    exchange_upper = (exchange or "").strip().upper()
                    if exchange_upper == "SG":
                        tz = pytz.timezone('Asia/Singapore')
                    elif exchange_upper in ["TO", "TSE", "V", "TSX", "NEO", "CSE"]:
                        tz = pytz.timezone('America/Toronto')
                    else:
                        tz = pytz.timezone('America/New_York')

                    local_now = datetime.now(tz)
                    local_date_str = local_now.strftime("%Y-%m-%d")
                    is_local_weekday = local_now.weekday() <= 4

                    reset_pnl = False
                    # 1. Holiday: Stock missed a global trading day
                    if global_last_date_str and last_date_str < global_last_date_str:
                        reset_pnl = True

                    if reset_pnl:
                        prev_close = intraday_price
                    # -----------------------------------------

                    # Determine if the market is open today for this exchange (using local exchange time)
                    local_time = local_now.time()
                    market_closed = True
                    if is_local_weekday:
                        exchange_upper = (exchange or "").strip().upper()
                        if exchange_upper == "SG":
                            # SGX open: 9:00 AM - 12:00 PM and 1:00 PM - 5:00 PM SGT
                            if (time(9, 0) <= local_time < time(12, 0)) or (time(13, 0) <= local_time < time(17, 0)):
                                market_closed = False
                        else:
                            # US/Canada open: 9:30 AM - 4:00 PM EST/EDT
                            if time(9, 30) <= local_time < time(16, 0):
                                market_closed = False
                            
                    today_str = local_date_str
                    if last_date_str == today_str:
                        if not market_closed:
                            # Today is active/trading and market is still open, so yesterday is the latest completed daily close price
                            closing_price = prev_close
                            prev_closing_price = float(series.iloc[-3]) if len(series) >= 3 else prev_close
                        else:
                            # Market is closed today, so today's completed close is today's price
                            closing_price = intraday_price
                            prev_closing_price = prev_close
                    else:
                        # Today's daily bar is not yet in history, so the latest completed close is the last bar in the main df history
                        if not series.empty:
                            closing_price = float(series.iloc[-1])
                            prev_closing_price = float(series.iloc[-2]) if len(series) >= 2 else closing_price
                        else:
                            closing_price = intraday_price
                            prev_closing_price = intraday_price
                    
                    # Store currency (yfinance info isn't bulk-downloadable via history,
                    # so we preserve the existing currency or default from transactions)
                    cursor.execute("SELECT currency FROM transactions WHERE ticker_id = ? LIMIT 1", (ticker_id,))
                    tx_currency = cursor.fetchone()
                    currency = tx_currency['currency'] if tx_currency else "USD"
                    
                    updated_records.append((ticker_id, intraday_price, prev_close, closing_price, prev_closing_price, intraday_price, currency, now_str))
            except Exception as ex:
                logger.error("Error parsing price for %s: %s", yf_sym, ex)
                
        # Write back to SQLite
        if updated_records:
            with conn:
                conn.executemany("""
                    INSERT INTO ticker_prices (ticker_id, price, prev_close, closing_price, prev_closing_price, intraday_price, currency, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker_id) DO UPDATE SET
                        price = excluded.price,
                        prev_close = excluded.prev_close,
                        closing_price = excluded.closing_price,
                        prev_closing_price = excluded.prev_closing_price,
                        intraday_price = excluded.intraday_price,
                        currency = excluded.currency,
                        last_updated = excluded.last_updated
                """, updated_records)
                
            return {"status": "success", "message": f"Successfully updated {len(updated_records)} ticker prices."}
        else:
            return {"status": "success", "message": "No ticker prices could be extracted."}
            
    except Exception as e:
        logger.error("yfinance download failed: %s", e)
        return {"status": "error", "message": str(e)}
    finally:
        if close_on_exit:
            conn.close()

def can_refresh() -> bool:
    """Helper to check if manual refresh cooldown has passed."""
    global _last_refresh_time
    if _last_refresh_time is None:
        return True
    return get_now_utc() - _last_refresh_time >= REFRESH_COOLDOWN

def record_refresh():
    """Records the timestamp of a manual refresh."""
    global _last_refresh_time
    _last_refresh_time = get_now_utc()
