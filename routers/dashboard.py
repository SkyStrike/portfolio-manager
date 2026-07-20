import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from core.database import get_connection
from core.calculations import get_portfolio_summary
from core.cache import clear_dashboard_cache, get_cached_view
from services.fetch_exchange_rates import get_exchange_rates
from services.rebuild_dashboard import rebuild_all_views

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/dashboard/summary")
def get_summary(portfolio_id: int | None = None):
    logger.info("GET /api/dashboard/summary (portfolio_id=%s)", portfolio_id)
    conn = get_connection()
    try:
        rates = get_exchange_rates()
        summary = get_portfolio_summary(portfolio_id, conn, rates)
        return summary
    finally:
        conn.close()

@router.post("/api/dashboard/rebuild")
def trigger_rebuild(background_tasks: BackgroundTasks, sync: bool = False, ingest_ibkr_cash: bool = False):
    logger.info("POST /api/dashboard/rebuild (sync=%s, ingest_ibkr_cash=%s)", sync, ingest_ibkr_cash)
    clear_dashboard_cache()
    if sync:
        try:
            logger.info("Rebuilding dashboard synchronously (intraday + closing)...")
            rebuild_all_views(price_mode="intraday", ingest_ibkr_cash=ingest_ibkr_cash)
            rebuild_all_views(price_mode="closing", ingest_ibkr_cash=ingest_ibkr_cash)
            # Pre-populate cache
            get_cached_view("portfolio_active.html", "intraday", force=True, ingest_ibkr_cash=ingest_ibkr_cash)
            get_cached_view("portfolio_active.html", "closing", force=True, ingest_ibkr_cash=ingest_ibkr_cash)
            logger.info("Dashboard rebuild complete (sync).")
            return {"status": "success", "message": "Dashboard rebuilt successfully."}
        except Exception as e:
            logger.error("Dashboard rebuild failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Rebuild failed: {str(e)}")
    else:
        logger.info("Dashboard rebuild queued as background task.")
        background_tasks.add_task(rebuild_all_views, price_mode="intraday", ingest_ibkr_cash=ingest_ibkr_cash)
        background_tasks.add_task(rebuild_all_views, price_mode="closing", ingest_ibkr_cash=ingest_ibkr_cash)
        return {"status": "success", "message": "Dashboard rebuild task started in the background."}
@router.post("/api/dashboard/rebuild-spa")
def trigger_spa_rebuild(background_tasks: BackgroundTasks, sync: bool = False):
    """
    Lightweight rebuild for the SPA dashboard — generates JSON data only,
    skipping HTML template rendering. ~1-1.5s faster than /api/dashboard/rebuild.
    """
    logger.info("POST /api/dashboard/rebuild-spa (sync=%s)", sync)

    def _rebuild_spa():
        from services.rebuild_dashboard import generate_views_in_memory
        from core.database import get_connection
        from core.cache import _dashboard_cache
        conn = get_connection()
        try:
            for price_mode in ("intraday", "closing"):
                views = generate_views_in_memory(
                    conn, price_mode=price_mode
                )
                # Merge only the JSON keys into the existing cache
                if price_mode in _dashboard_cache and _dashboard_cache[price_mode]:
                    _dashboard_cache[price_mode].update(views)
                else:
                    _dashboard_cache[price_mode] = views
            logger.info("[rebuild-spa] SPA JSON cache refreshed.")
        finally:
            conn.close()

    if sync:
        try:
            _rebuild_spa()
            return {"status": "success", "message": "SPA cache refreshed (JSON only)."}
        except Exception as e:
            logger.error("SPA rebuild failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"SPA rebuild failed: {str(e)}")
    else:
        background_tasks.add_task(_rebuild_spa)
        return {"status": "success", "message": "SPA rebuild started in background."}
