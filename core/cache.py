import logging
import os
import time
import json
import threading
from fastapi.responses import HTMLResponse, JSONResponse
from core.database import get_connection

logger = logging.getLogger(__name__)

# In-memory dashboard cache
# Structure: { price_mode: { filename: content_string_or_dict } }
_dashboard_cache = {
    "intraday": {},
    "closing": {}
}

# Cache timestamps to expire every 60 minutes
_cache_timestamp = {
    "intraday": 0.0,
    "closing": 0.0
}

# Rebuild lock for background tasks
_rebuild_lock = {
    "intraday": False,
    "closing": False
}

CACHE_TTL = 3600  # 60 minutes

base_path = os.getenv("BASE_PATH", "").strip()
if base_path and not base_path.startswith("/"):
    base_path = "/" + base_path

def clear_dashboard_cache(price_mode: str = None):
    global _dashboard_cache, _cache_timestamp
    if price_mode:
        m = price_mode.lower()
        if m in _dashboard_cache:
            _dashboard_cache[m] = {}
            _cache_timestamp[m] = 0.0
    else:
        _dashboard_cache = {
            "intraday": {},
            "closing": {}
        }
        _cache_timestamp = {
            "intraday": 0.0,
            "closing": 0.0
        }

def _bg_rebuild(price_mode: str):
    global _dashboard_cache, _cache_timestamp, _rebuild_lock
    logger.info("[cache] TTL expired — starting background cache rebuild (price_mode=%s)", price_mode)
    try:
        from services.rebuild_dashboard import generate_views_in_memory
        conn = get_connection()
        try:
            views = generate_views_in_memory(conn, price_mode=price_mode)
            _dashboard_cache[price_mode] = views
            _cache_timestamp[price_mode] = time.time()
            logger.info("[cache] Background cache rebuild complete (price_mode=%s, views=%d)", price_mode, len(views))
        finally:
            conn.close()
    except Exception as e:
        logger.error("Background cache rebuild failed for %s: %s", price_mode, e)
    finally:
        _rebuild_lock[price_mode] = False

def get_cached_view(filename: str, price_mode: str, force: bool = False, ingest_ibkr_cash: bool = False):
    global _dashboard_cache, _cache_timestamp, _rebuild_lock
    
    price_mode = price_mode.lower()
    if price_mode not in ("intraday", "closing"):
        price_mode = "intraday"
        
    # Normalize filename: remove any price mode suffix (like _intraday or _closing)
    base, ext = os.path.splitext(filename)
    for m in ("intraday", "closing"):
        if base.endswith(f"_{m}"):
            base = base[:-len(f"_{m}")]
    normalized_filename = f"{base}{ext}"
    
    now = time.time()
    cache_exists = bool(_dashboard_cache[price_mode])
    cache_expired = (now - _cache_timestamp[price_mode] > CACHE_TTL)
 
    # Check if cache is empty, or force rebuild requested
    if force or not cache_exists:
        try:
            from services.rebuild_dashboard import generate_views_in_memory, ingest_ibkr_cash_from_file
            conn = get_connection()
            try:
                if ingest_ibkr_cash:
                    ingest_ibkr_cash_from_file(conn)
                views = generate_views_in_memory(conn, price_mode=price_mode)
                _dashboard_cache[price_mode] = views
                _cache_timestamp[price_mode] = now
            finally:
                conn.close()
        except Exception as e:
            import traceback
            traceback.print_exc()
            return HTMLResponse(f"<h3>Error rendering view in memory: {str(e)}</h3>", status_code=500)
    elif cache_expired:
        # Cache is expired but exists. Trigger background update and serve stale cache.
        if not _rebuild_lock[price_mode]:
            _rebuild_lock[price_mode] = True
            t = threading.Thread(target=_bg_rebuild, args=(price_mode,))
            t.daemon = True
            t.start()
            
    # Lookup normalized filename in cache
    views = _dashboard_cache[price_mode]
    if normalized_filename in views:
        content = views[normalized_filename]
        if normalized_filename.endswith(".html"):
            return HTMLResponse(content=content)
        elif normalized_filename.endswith(".json"):
            return JSONResponse(content=content)
        else:
            return HTMLResponse(content=str(content))
            
    # Try direct filesystem lookup if it's a static file (e.g. ib_data.json)
    if normalized_filename.startswith("src/"):
        clean_name = normalized_filename[4:]  # remove src/
        data_path = f"config/{clean_name}"
        if not os.path.exists(data_path):
            data_path = f"data/{clean_name}"
        if os.path.exists(data_path):
            with open(data_path, 'r', encoding='utf-8') as f:
                try:
                    return JSONResponse(content=json.load(f))
                except Exception:
                    pass
                    
    return HTMLResponse("<h3>Page not found.</h3>", status_code=404)

def rebuild_dashboard_sync(conn=None, price_mode=None, ingest_ibkr_cash=False):
    logger.info("[rebuild_dashboard_sync] Clearing cache and rebuilding...")
    clear_dashboard_cache()
    if price_mode:
        get_cached_view("portfolio_active.html", price_mode, force=True, ingest_ibkr_cash=ingest_ibkr_cash)
    logger.info("[rebuild_dashboard_sync] Done.")

def update_prices_and_rebuild(ingest_ibkr_cash=False):
    logger.info("[update_prices_and_rebuild] Starting price update and full dashboard rebuild (ingest_ibkr_cash=%s)...", ingest_ibkr_cash)
    from services.price_service import update_prices
    from services.dividend_service import sync_upcoming_dividends
    conn = get_connection()
    try:
        logger.info("[update_prices_and_rebuild] Fetching latest prices from yfinance...")
        update_prices(conn, force=True)
        try:
            logger.info("[update_prices_and_rebuild] Syncing upcoming dividends...")
            sync_upcoming_dividends(conn, force=True)
        except Exception as e:
            logger.warning("Failed to sync upcoming dividends during update: %s", e)
        logger.info("[update_prices_and_rebuild] Rebuilding dashboard cache (intraday + closing)...")
        clear_dashboard_cache()
        # Pre-populate both price modes in memory
        get_cached_view("portfolio_active.html", "intraday", force=True, ingest_ibkr_cash=ingest_ibkr_cash)
        get_cached_view("portfolio_active.html", "closing", force=True, ingest_ibkr_cash=ingest_ibkr_cash)
        logger.info("[update_prices_and_rebuild] Complete.")
    finally:
        conn.close()

def serve_rebuilt_page(filename: str, price_mode: str) -> HTMLResponse | JSONResponse:
    return get_cached_view(filename, price_mode)

def get_cached_portfolio_data(price_mode: str = "closing", force: bool = False) -> dict:
    """Provides strongly-typed in-memory access to portfolio data payload."""
    mode = "closing" if price_mode == "closing" else "intraday"
    if force or not _dashboard_cache[mode]:
        get_cached_view("portfolio_active.html", mode, force=force)
    views = _dashboard_cache[mode]
    data = views.get("src/portfolio_data.json")
    return data if isinstance(data, dict) else {}

def get_cached_dividend_calendar(price_mode: str = "closing", force: bool = False) -> dict:
    """Provides strongly-typed in-memory access to dividend calendar payload."""
    mode = "closing" if price_mode == "closing" else "intraday"
    if force or not _dashboard_cache[mode]:
        get_cached_view("portfolio_active.html", mode, force=force)
    views = _dashboard_cache[mode]
    data = views.get("src/dividend_calendar_data.json")
    return data if isinstance(data, dict) else {}

