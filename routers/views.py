import logging
import os
from fastapi import APIRouter, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from core.cache import get_cached_view, base_path

logger = logging.getLogger(__name__)

router = APIRouter()

# Primary SPA Dashboard Routes
@router.get("/", response_class=HTMLResponse)
@router.get("/active", response_class=HTMLResponse)
@router.get("/closed", response_class=HTMLResponse)
@router.get("/history", response_class=HTMLResponse)
@router.get("/charts", response_class=HTMLResponse)
@router.get("/performance", response_class=HTMLResponse)
@router.get("/dividend-calendar", response_class=HTMLResponse)
@router.get("/fd-comparison", response_class=HTMLResponse)
def get_spa_dashboard():
    logger.info("GET SPA Dashboard - serving SPA shell wrapped in base.html")
    if os.path.exists("templates/spa_shell.html"):
        from jinja2 import Environment, FileSystemLoader
        from services.rebuild_dashboard import load_config
        from core.database import get_connection
        
        conn = get_connection()
        nav_items = [{"name": "All", "url": f"{base_path}/", "id": "nav-all", "slug": "all"}]
        category_nav = []
        portfolio_nav = []
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT classification FROM portfolios WHERE classification IS NOT NULL AND classification != ''")
            classifications = [row['classification'] for row in cursor.fetchall()]
            
            config = load_config()
            priority = config.get('sorting', {}).get('classification_priority', [])
            def class_sort_key(c_name):
                try: return (priority.index(c_name), c_name)
                except ValueError: return (100, c_name)
            classifications.sort(key=class_sort_key)
            
            from core.models import slugify
            for c in classifications:
                c_slug = slugify(c)
                category_nav.append({
                    "name": c,
                    "url": f"{base_path}/active?filter={c_slug}",
                    "id": f"nav-{c_slug}",
                    "slug": c_slug
                })
                
            cursor.execute("SELECT id, name, broker, classification FROM portfolios ORDER BY name")
            portfolios = cursor.fetchall()
            for port in portfolios:
                pslug = port['name'].lower().replace(" ", "-")
                portfolio_nav.append({
                    "name": port['name'],
                    "url": f"{base_path}/active?filter=port-{pslug}",
                    "id": f"port-{pslug}",
                    "slug": f"port-{pslug}",
                    "broker": port['broker'] or '',
                })
        except Exception as e:
            logger.error("Error fetching portfolios for navigation: %s", e)
        finally:
            conn.close()

        env = Environment(loader=FileSystemLoader("templates"))
        spa_template = env.get_template("spa_shell.html")
        
        config = load_config()
        page_width = config.get("ui", {}).get("page_width", "1800px")
        
        js_template = env.get_template("scripts.js")
        ui_config = config.get("ui", {})
        colors_config = config.get("colors", {})
        font_style = ui_config.get("typography", {}).get("font_family", "sans-serif")
        js_content = js_template.render(
            FONT_STYLE=font_style,
            BASE_PATH=base_path,
            COLOR_INVESTED=colors_config.get("invested", "#8b5cf6"),
            COLOR_CURRENT=colors_config.get("current", "#3498db"),
            COLOR_RETURNS=colors_config.get("returns", "#2ecc71"),
            COLOR_INCOME=colors_config.get("income", "#2ecc71"),
            COLOR_POSITIVE=colors_config.get("positive", "#3498db"),
            COLOR_NEGATIVE=colors_config.get("negative", "#e74c3c"),
            UI_FONT_SIZE=ui_config.get("font_size", "14px"),
            UI_MOBILE_FONT_SIZE=ui_config.get("mobile_font_size", "12px")
        )
        
        options_tracker_url = config.get("external_services", {}).get("options_tracker_url", "")
        if "/api/positions" in options_tracker_url:
            options_tracker_main_url = options_tracker_url.replace("/api/positions", "")
        else:
            options_tracker_main_url = options_tracker_url
        backtester_url = config.get("external_services", {}).get("backtester_url", "")
        
        rendered = spa_template.render(
            TITLE="Portfolio Manager - Dashboard",
            page_title="Dashboard",
            JS=js_content,
            PAGE_WIDTH=page_width,
            BASE_PATH=base_path,
            OPTIONS_TRACKER_URL=options_tracker_main_url,
            BACKTESTER_URL=backtester_url,
            nav_items=nav_items,
            category_nav=category_nav,
            portfolio_nav=portfolio_nav,
            NAV_ITEMS=nav_items,
            CAT_NAV=category_nav,
            PORT_NAV=portfolio_nav,
            JSON_FILENAME="portfolio_data_intraday.json"
        )
        return HTMLResponse(content=rendered)
    return HTMLResponse("<h3>Please create templates/spa_shell.html</h3>")



# Dynamic source JSON routing
@router.get("/static/generated/src/{filename}")
@router.get("/src/{filename}")
def get_json_file(filename: str, price_mode: str = "intraday"):
    logger.debug("GET /src/%s (price_mode=%s)", filename, price_mode)
    base, ext = os.path.splitext(filename)
    for m in ("intraday", "closing"):
        if base.endswith(f"_{m}"):
            price_mode = m
            base = base[:-len(f"_{m}")]
            
    normalized_key = f"src/{base}{ext}"
    return get_cached_view(normalized_key, price_mode)

# Beta SPA Route (Redirected to Root)
@router.get("/beta")
def redirect_beta():
    logger.info("GET /beta - redirecting to primary SPA dashboard root /")
    return RedirectResponse(url=f"{base_path}/", status_code=307)

# Trades Ledger SPA Route
@router.get("/trades", response_class=HTMLResponse)
def get_trades():
    logger.info("GET /trades - serving trades SPA")
    if os.path.exists("templates/trades.html"):
        from jinja2 import Environment, FileSystemLoader
        from services.rebuild_dashboard import load_config
        config = load_config()
        options_tracker_url = config.get("external_services", {}).get("options_tracker_url", "")
        if "/api/positions" in options_tracker_url:
            options_tracker_main_url = options_tracker_url.replace("/api/positions", "")
        else:
            options_tracker_main_url = options_tracker_url
        backtester_url = config.get("external_services", {}).get("backtester_url", "")
        metrics_run_hour = config.get("cron", {}).get("metrics_run_hour", 6)
        brokers = config.get("brokers", ["IBKR", "MOOMOO"])

        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template("trades.html")
        rendered = template.render(
            BASE_PATH=base_path,
            OPTIONS_TRACKER_URL=options_tracker_main_url,
            BACKTESTER_URL=backtester_url,
            METRICS_RUN_HOUR=metrics_run_hour,
            BROKERS=brokers
        )
        return HTMLResponse(content=rendered)
    return HTMLResponse("<h3>Please place templates/trades.html</h3>")

# Control Center SPA Route
@router.get("/control-center", response_class=HTMLResponse)
def get_control_center():
    logger.info("GET /control-center - serving control center SPA")
    if os.path.exists("templates/control_center.html"):
        from jinja2 import Environment, FileSystemLoader
        from services.rebuild_dashboard import load_config
        config = load_config()
        options_tracker_url = config.get("external_services", {}).get("options_tracker_url", "")
        if "/api/positions" in options_tracker_url:
            options_tracker_main_url = options_tracker_url.replace("/api/positions", "")
        else:
            options_tracker_main_url = options_tracker_url
        backtester_url = config.get("external_services", {}).get("backtester_url", "")
        metrics_run_hour = config.get("cron", {}).get("metrics_run_hour", 6)
        brokers = config.get("brokers", ["IBKR", "MOOMOO"])

        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template("control_center.html")
        rendered = template.render(
            BASE_PATH=base_path,
            OPTIONS_TRACKER_URL=options_tracker_main_url,
            BACKTESTER_URL=backtester_url,
            METRICS_RUN_HOUR=metrics_run_hour,
            BROKERS=brokers
        )
        return HTMLResponse(content=rendered)
    return HTMLResponse("<h3>Please place templates/control_center.html</h3>")



# Fixed Deposit Simulation API
@router.post("/api/fd-comparison")
async def post_fd_comparison(
    rate_mode: str = Form("fixed"),
    fixed_rate: float = Form(2.0),
    file: UploadFile = File(None)
):
    logger.info("POST /api/fd-comparison - running FD simulation (rate_mode=%s, fixed_rate=%s)", rate_mode, fixed_rate)
    from services.fd_simulator import run_fd_simulation
    
    csv_content = None
    if file:
        try:
            bytes_content = await file.read()
            csv_content = bytes_content.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error("Error reading uploaded FD rates CSV: %s", e)
            
    try:
        result = run_fd_simulation(rate_mode, fixed_rate, csv_content)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("Error running FD simulation: %s", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

