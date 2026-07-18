import os
import asyncio

import logging
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from core.database import init_db
from core.migrations import run_migrations
from core.cache import clear_dashboard_cache, get_cached_view, base_path
from routers import views, portfolios, tickers, transactions, dividends, prices, dashboard, reports, uploads, settings, patches

# Run Alembic migrations first, then initialize static schema guards
run_migrations()
init_db()

# Create FastAPI app
main_app = FastAPI(title="Portfolio Manager")

# CORS middleware configuration
main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def hourly_rebuild_loop():
    while True:
        try:
            await asyncio.sleep(3600)
            logger.info("[cron/hourly] Triggering hourly dashboard cache refresh...")
            clear_dashboard_cache()
            get_cached_view("portfolio_active.html", "intraday", force=True)
            get_cached_view("portfolio_active.html", "closing", force=True)
            logger.info("[cron/hourly] Hourly dashboard refresh complete.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in hourly rebuild background loop: %s", e)
            await asyncio.sleep(60)

async def daily_weekday_metrics_job():
    import pytz
    from datetime import datetime

    while True:
        try:
            from core.cache import update_prices_and_rebuild
            # Check timezone - SGT (GMT+8)
            sgt_tz = pytz.timezone('Asia/Singapore')
            now_sgt = datetime.now(sgt_tz)

            # Load config to get the metrics run hour dynamically
            from services.rebuild_dashboard import load_config
            config = load_config()
            target_hour = config.get("cron", {}).get("metrics_run_hour", 6)

            # NYSE closes at 4:00 PM EST (which is 4:00 AM SGT next day, or 5:00 AM during Standard Time)
            # Run sync at target_hour SGT (Tuesday to Saturday mornings, matching Mon-Fri trading days)
            # Weekday integers: 0=Monday, ..., 5=Saturday (Tuesday-Saturday morning represents Mon-Fri close)
            is_trading_run = now_sgt.weekday() in [1, 2, 3, 4, 5]

            # Target hour: configured metrics_run_hour (default 6 AM SGT)
            if is_trading_run and now_sgt.hour == target_hour:
                logger.info(
                    "[cron/daily] Triggering automated daily metrics recording for %s SGT at target hour %s...",
                    now_sgt.date(), target_hour
                )

                # Warm today's exchange rates into the in-memory cache before
                # any transaction writes can trigger on-demand API fetches.
                from services.fetch_exchange_rates import warm_today_exchange_rates
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, warm_today_exchange_rates)

                # Perform price fetch, update cash reports, and rebuild views (which records metrics to DB)
                await loop.run_in_executor(None, lambda: update_prices_and_rebuild(ingest_ibkr_cash=True))
                logger.info("[cron/daily] Automated daily metrics job complete for %s.", now_sgt.date())

                # Sleep for 1 hour to prevent double trigger within the same configured hour
                await asyncio.sleep(3600)

            # Sleep 15 minutes before checking again
            await asyncio.sleep(900)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in automated daily job: %s", e)
            await asyncio.sleep(300)

def prewarm_cache():
    logger.info("[startup] Prewarming dashboard cache (intraday + closing)...")
    try:
        from services.fetch_exchange_rates import warm_today_exchange_rates
        warm_today_exchange_rates()
        clear_dashboard_cache()
        get_cached_view("portfolio_active.html", "intraday")
        get_cached_view("portfolio_active.html", "closing")
        logger.info("[startup] Cache prewarm complete.")
    except Exception as e:
        logger.error("Initial startup prewarm failed: %s", e)

# Mount static folders
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("tmp", exist_ok=True)

# Include sub-routers
main_app.include_router(views.router)
main_app.include_router(portfolios.router, tags=["portfolios"])
main_app.include_router(tickers.router, tags=["tickers"])
main_app.include_router(transactions.router, tags=["transactions"])
main_app.include_router(dividends.router, tags=["dividends"])
main_app.include_router(prices.router, tags=["prices"])
main_app.include_router(dashboard.router, tags=["dashboard"])
main_app.include_router(reports.router, tags=["reports"])
main_app.include_router(uploads.router, tags=["uploads"])
main_app.include_router(settings.router, tags=["settings"])
main_app.include_router(patches.router, tags=["patches"])

# Mount static folder
main_app.mount("/static", StaticFiles(directory="static"), name="static")

# If base_path is set (reverse-proxy sub-path deployment), mount base app
if base_path:
    parent_app = FastAPI(title="Portfolio Manager Parent")
    parent_app.mount(base_path, main_app)
    app = parent_app
else:
    app = main_app

@app.on_event("startup")
async def startup_event():
    from core.logging_config import configure_logging
    configure_logging()
    logger.info("[startup] Portfolio Manager starting up...")





    import threading
    t = threading.Thread(target=prewarm_cache)
    t.daemon = True
    t.start()
    asyncio.create_task(hourly_rebuild_loop())
    asyncio.create_task(daily_weekday_metrics_job())

