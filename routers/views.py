import logging
import os
from fastapi import APIRouter, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from core.cache import get_cached_view, base_path

logger = logging.getLogger(__name__)

router = APIRouter()

# Redirect legacy routes to primary SPA dashboard
@router.get("/legacy")
@router.get("/legacy/{path:path}")
def redirect_legacy_to_spa(path: str = ""):
    logger.info("Redirecting legacy route '/legacy/%s' to SPA dashboard", path)
    return RedirectResponse(url=f"{base_path}/", status_code=301)


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
                    "url": f"{base_path}/portfolio_active_{c_slug}.html",
                    "id": f"nav-{c_slug}",
                    "slug": c_slug
                })
                
            cursor.execute("SELECT id, name, broker, classification FROM portfolios ORDER BY name")
            portfolios = cursor.fetchall()
            for port in portfolios:
                pslug = port['name'].lower().replace(" ", "-")
                portfolio_nav.append({
                    "name": port['name'],
                    "url": f"{base_path}/portfolio_active_port_{pslug}.html",
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
        spa_content = spa_template.render(BASE_PATH=base_path)
        
        config = load_config()
        page_width = config.get("ui", {}).get("page_width", "1800px")
        from services.css_helper import render_combined_css
        css_content = render_combined_css(env, page_width=page_width)
        
        js_template = env.get_template("scripts.js")
        config = load_config()
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
        
        base_template = env.get_template("base.html")
        page_width = config.get("ui", {}).get("page_width", "1800px")
        options_tracker_url = config.get("external_services", {}).get("options_tracker_url", "")
        if "/api/positions" in options_tracker_url:
            options_tracker_main_url = options_tracker_url.replace("/api/positions", "")
        else:
            options_tracker_main_url = options_tracker_url
        backtester_url = config.get("external_services", {}).get("backtester_url", "")
        
        wrapped = base_template.render(
            TITLE="Dashboard",
            page_title="Dashboard",
            CONTENT=spa_content,
            body_content=spa_content,
            CSS=css_content,
            JS=js_content,
            PAGE_WIDTH=page_width,
            BASE_PATH=base_path,
            OPTIONS_TRACKER_URL=options_tracker_main_url,
            BACKTESTER_URL=backtester_url,
            nav_items=nav_items,
            category_nav=category_nav,
            portfolio_nav=portfolio_nav,
            JSON_FILENAME="portfolio_data_intraday.json"
        )
        return HTMLResponse(content=wrapped)
    return HTMLResponse("<h3>Please create templates/spa_shell.html</h3>")


# Legacy .html alias redirects (301 Permanent) → canonical SPA paths
@router.get("/portfolio_active.html")
def redirect_portfolio_active(): return RedirectResponse(url=f"{base_path}/active", status_code=301)

@router.get("/portfolio_closed.html")
def redirect_portfolio_closed(): return RedirectResponse(url=f"{base_path}/closed", status_code=301)

@router.get("/transaction_history.html")
def redirect_transaction_history(): return RedirectResponse(url=f"{base_path}/history", status_code=301)

@router.get("/charts.html")
def redirect_charts(): return RedirectResponse(url=f"{base_path}/charts", status_code=301)

@router.get("/performance_report.html")
def redirect_performance_report(): return RedirectResponse(url=f"{base_path}/performance", status_code=301)

@router.get("/dividend_calendar.html")
def redirect_dividend_calendar(): return RedirectResponse(url=f"{base_path}/dividend-calendar", status_code=301)

@router.get("/portfolio_active_{slug}.html")
@router.get("/portfolio_closed_{slug}.html")
@router.get("/transaction_history_{slug}.html")
@router.get("/charts_{slug}.html")
@router.get("/performance_report_{slug}.html")
@router.get("/portfolio_active_port_{slug}.html")
@router.get("/portfolio_closed_port_{slug}.html")
@router.get("/transaction_history_port_{slug}.html")
@router.get("/charts_port_{slug}.html")
def redirect_legacy_slug_html(slug: str):
    logger.info("Redirecting legacy slug .html route (slug=%s) to SPA root", slug)
    return RedirectResponse(url=f"{base_path}/", status_code=301)


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



@router.get("/analytics/fd-comparison")
def redirect_fd_comparison_legacy():
    """Legacy redirect — keep old deep-links working."""
    logger.info("GET /analytics/fd-comparison - redirecting to /fd-comparison")
    return RedirectResponse(url=f"{base_path}/fd-comparison", status_code=301)

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

