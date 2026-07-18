import logging
import os
from fastapi import APIRouter, Form, File, UploadFile
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from core.cache import serve_rebuilt_page, get_cached_view, base_path

logger = logging.getLogger(__name__)

router = APIRouter()

# Legacy HTML Page Routes (Static Dashboards Backup)
@router.get("/legacy", response_class=HTMLResponse)
@router.get("/legacy/active", response_class=HTMLResponse)
@router.get("/legacy/portfolio_active.html", response_class=HTMLResponse)
def get_legacy_active(price_mode: str = "intraday"):
    logger.debug("GET /legacy (portfolio_active, price_mode=%s)", price_mode)
    return serve_rebuilt_page("portfolio_active.html", price_mode)

@router.get("/legacy/closed", response_class=HTMLResponse)
@router.get("/legacy/portfolio_closed.html", response_class=HTMLResponse)
def get_legacy_closed(price_mode: str = "intraday"):
    logger.debug("GET /legacy/closed (price_mode=%s)", price_mode)
    return serve_rebuilt_page("portfolio_closed.html", price_mode)

@router.get("/legacy/history", response_class=HTMLResponse)
@router.get("/legacy/transaction_history.html", response_class=HTMLResponse)
def get_legacy_history(price_mode: str = "intraday"):
    logger.debug("GET /legacy/history (price_mode=%s)", price_mode)
    return serve_rebuilt_page("transaction_history.html", price_mode)

@router.get("/legacy/charts.html", response_class=HTMLResponse)
def get_legacy_charts(price_mode: str = "intraday"):
    logger.debug("GET /legacy/charts.html (price_mode=%s)", price_mode)
    return serve_rebuilt_page("charts.html", price_mode)

@router.get("/legacy/performance_report.html", response_class=HTMLResponse)
def get_legacy_performance_report_view(price_mode: str = "intraday"):
    logger.debug("GET /legacy/performance_report.html (price_mode=%s)", price_mode)
    return serve_rebuilt_page("performance_report.html", price_mode)

@router.get("/legacy/dividend-calendar", response_class=HTMLResponse)
@router.get("/legacy/dividend_calendar.html", response_class=HTMLResponse)
def get_legacy_dividend_calendar(price_mode: str = "intraday"):
    logger.debug("GET /legacy/dividend-calendar (price_mode=%s)", price_mode)
    return serve_rebuilt_page("dividend_calendar.html", price_mode)

@router.get("/legacy/portfolio_active_{slug}.html", response_class=HTMLResponse)
def get_legacy_active_category(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/portfolio_active_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"portfolio_active_{slug}.html", price_mode)

@router.get("/legacy/portfolio_closed_{slug}.html", response_class=HTMLResponse)
def get_legacy_closed_category(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/portfolio_closed_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"portfolio_closed_{slug}.html", price_mode)

@router.get("/legacy/transaction_history_{slug}.html", response_class=HTMLResponse)
def get_legacy_history_category(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/transaction_history_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"transaction_history_{slug}.html", price_mode)

@router.get("/legacy/charts_{slug}.html", response_class=HTMLResponse)
def get_legacy_charts_category(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/charts_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"charts_{slug}.html", price_mode)

@router.get("/legacy/performance_report_{slug}.html", response_class=HTMLResponse)
def get_legacy_performance_category(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/performance_report_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"performance_report_{slug}.html", price_mode)

@router.get("/legacy/portfolio_active_port_{slug}.html", response_class=HTMLResponse)
def get_legacy_active_portfolio(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/portfolio_active_port_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"portfolio_active_port_{slug}.html", price_mode)

@router.get("/legacy/portfolio_closed_port_{slug}.html", response_class=HTMLResponse)
def get_legacy_closed_portfolio(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/portfolio_closed_port_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"portfolio_closed_port_{slug}.html", price_mode)

@router.get("/legacy/transaction_history_port_{slug}.html", response_class=HTMLResponse)
def get_legacy_history_portfolio(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/transaction_history_port_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"transaction_history_port_{slug}.html", price_mode)

@router.get("/legacy/charts_port_{slug}.html", response_class=HTMLResponse)
def get_legacy_charts_portfolio(slug: str, price_mode: str = "intraday"):
    logger.debug("GET /legacy/charts_port_%s.html (price_mode=%s)", slug, price_mode)
    return serve_rebuilt_page(f"charts_port_{slug}.html", price_mode)


# Primary SPA Dashboard Routes
@router.get("/", response_class=HTMLResponse)
@router.get("/active", response_class=HTMLResponse)
@router.get("/portfolio_active.html", response_class=HTMLResponse)
@router.get("/closed", response_class=HTMLResponse)
@router.get("/portfolio_closed.html", response_class=HTMLResponse)
@router.get("/history", response_class=HTMLResponse)
@router.get("/transaction_history.html", response_class=HTMLResponse)
@router.get("/charts.html", response_class=HTMLResponse)
@router.get("/performance_report.html", response_class=HTMLResponse)
@router.get("/dividend-calendar", response_class=HTMLResponse)
@router.get("/dividend_calendar.html", response_class=HTMLResponse)
@router.get("/portfolio_active_{slug}.html", response_class=HTMLResponse)
@router.get("/portfolio_closed_{slug}.html", response_class=HTMLResponse)
@router.get("/transaction_history_{slug}.html", response_class=HTMLResponse)
@router.get("/charts_{slug}.html", response_class=HTMLResponse)
@router.get("/performance_report_{slug}.html", response_class=HTMLResponse)
@router.get("/portfolio_active_port_{slug}.html", response_class=HTMLResponse)
@router.get("/portfolio_closed_port_{slug}.html", response_class=HTMLResponse)
@router.get("/transaction_history_port_{slug}.html", response_class=HTMLResponse)
@router.get("/charts_port_{slug}.html", response_class=HTMLResponse)
def get_spa_dashboard():
    logger.info("GET SPA Dashboard - serving SPA shell wrapped in base.html")
    if os.path.exists("templates/spa_shell.html"):
        from jinja2 import Environment, FileSystemLoader
        from services.rebuild_dashboard import load_config
        from core.database import get_connection
        from services.report_renderer import ReportRenderer
        
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
        
        # Instantiate a mock renderer to get base layout wrapping
        dummy_data = {
            "metadata": {
                "config": {},
                "summary": {
                    "total_market_value_sgd": 0, 
                    "total_invested_active_sgd": 0,
                    "total_capital_gains_sgd": 0,
                    "total_capital_gains_pct": 0,
                    "lifetime_profit_sgd": 0
                }
            },
            "positions": [],
            "dashboard": {"daily_performance": {}}
        }
        renderer = ReportRenderer(dummy_data)
        
        wrapped = renderer._wrap_body(
            content=spa_content,
            title="Dashboard",
            is_closed=False,
            nav_items=nav_items,
            cat_nav=category_nav,
            port_nav=portfolio_nav,
            json_filename="portfolio_data_intraday.json"
        )
        return HTMLResponse(content=wrapped)
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

# Fixed Deposit Comparison view
@router.get("/fd-comparison", response_class=HTMLResponse)
def get_fd_comparison():
    logger.info("GET /fd-comparison - serving FD comparison page")
    
    # 1. Load active portfolio data from in-memory cache
    from core.cache import _dashboard_cache, get_cached_view
    if not _dashboard_cache["intraday"]:
        get_cached_view("portfolio_active.html", "intraday")
        
    data = _dashboard_cache["intraday"].get("src/portfolio_data.json")
    if not data:
        return HTMLResponse("<h3>Please run dashboard generation first.</h3>")
        
    from services.report_renderer import ReportRenderer, slugify
    renderer = ReportRenderer(data)
    
    # Reconstruct navigation lists
    nav_items = [{"name": "All", "url": "portfolio_active.html", "id": "pill-active"}]
    
    # Scan for category-specific JSONs in in-memory cache
    category_nav = []
    for filename in sorted(_dashboard_cache["intraday"].keys()):
        if filename.startswith("src/portfolio_data_") and filename.endswith(".json") and not filename.startswith("src/portfolio_data_port_"):
            slug = filename.replace("src/portfolio_data_", "").replace(".json", "")
            cat_data = _dashboard_cache["intraday"][filename]
            display_name = cat_data['metadata'].get('classification', slug.replace("-", " ").title())
            category_nav.append({
                "name": display_name,
                "url": f"portfolio_active_{slug}.html",
                "id": f"pill-active-{slug}",
                "slug": slug
            })

    # Scan for portfolios
    portfolio_nav = []
    from core.database import get_connection
    conn = get_connection()
    try:
        portfolios = conn.execute("SELECT id, name, broker, classification FROM portfolios").fetchall()
        for port in portfolios:
            pslug = slugify(port['name'])
            portfolio_nav.append({
                "name": port['name'],
                "url": f"portfolio_active_port_{pslug}.html",
                "id": f"pill-active-port-{pslug}",
                "slug": f"port-{pslug}",
                "broker": port['broker'] or '',
            })
    except Exception as e:
        logger.error("Error fetching portfolios for navigation: %s", e)
    finally:
        conn.close()

    if os.path.exists("templates/fixed_deposit_comparison.html"):
        env = renderer.env
        template = env.get_template("fixed_deposit_comparison.html")
        content = template.render(
            BASE_PATH=base_path,
            TITLE="vs Fixed Deposits"
        )
        
        wrapped = renderer._wrap_body(
            content=content,
            title="vs Fixed Deposits",
            is_closed=False,
            nav_items=nav_items,
            cat_nav=category_nav,
            port_nav=portfolio_nav
        )
        return HTMLResponse(content=wrapped)
    return HTMLResponse("<h3>Please place templates/fixed_deposit_comparison.html</h3>")

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

