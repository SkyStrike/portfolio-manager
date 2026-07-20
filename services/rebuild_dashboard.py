import logging
import os
import sys
import json
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Core imports
from core.models import Position, parse_val, slugify
from core.dashboard_builder import build_dashboard
from core.database import get_connection, DB_FILE
from services.fetch_exchange_rates import get_exchange_rates, get_historical_exchange_rate

# Trading date calculation
def calculate_trading_date():
    try:
        ny_tz = ZoneInfo("America/New_York")
    except Exception:
        # Fallback if America/New_York zoneinfo database is not fully loaded on OS
        ny_tz = timezone(timedelta(hours=-4)) # Standard approximation (or DST -4/-5)
        
    ny_now = datetime.now(timezone.utc).astimezone(ny_tz)
    
    # Shift back by 9.5 hours (NYSE Open is 9:30 AM)
    shifted = ny_now - timedelta(hours=9.5)
    
    # Map weekends to Friday (if shifted date is Saturday, subtract 1 day; if Sunday, subtract 2 days)
    weekday = shifted.weekday()
    if weekday == 5: # Saturday
        shifted = shifted - timedelta(days=1)
    elif weekday == 6: # Sunday
        shifted = shifted - timedelta(days=2)
        
    return shifted.strftime('%Y-%m-%d')

DEFAULT_OPTIONS_TRACKER_URL = ""
DEFAULT_BACKTESTER_URL = ""
DEFAULT_CLASSIFICATION_PRIORITY = []
DEFAULT_METRICS_RUN_HOUR = 6
DEFAULT_ALLOWED_DOCUMENTS = {
    "stock-options": "data/stock-options.json",
    "ib-data": "data/ib_data.json"
}

# Helper to load config
def load_config():
    config_path = "data/config.json"
    if not os.path.exists(config_path):
        config_path = "config/config.json"
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error("Error reading config.json: %s", e)
            
    # Merge overrides from SQLite settings table if it exists
    try:
        from core.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        if cursor.fetchone():
            cursor.execute("SELECT key, value FROM settings")
            for row in cursor.fetchall():
                key = row['key']
                val_json = row['value']
                try:
                    val = json.loads(val_json)
                except Exception:
                    val = val_json
                
                parts = key.split('.')
                curr = config
                for part in parts[:-1]:
                    if part not in curr or not isinstance(curr[part], dict):
                        curr[part] = {}
                    curr = curr[part]
                curr[parts[-1]] = val
        conn.close()
    except Exception as e:
        logger.error("Error loading config settings from database: %s", e)
        
    # Inject defaults for missing settings
    if "allowed_documents" not in config:
        config["allowed_documents"] = {}
    for k, v in DEFAULT_ALLOWED_DOCUMENTS.items():
        if k not in config["allowed_documents"] or not config["allowed_documents"][k]:
            config["allowed_documents"][k] = v

    if "external_services" not in config:
        config["external_services"] = {}
    if "options_tracker_url" not in config["external_services"] or not config["external_services"]["options_tracker_url"]:
        config["external_services"]["options_tracker_url"] = DEFAULT_OPTIONS_TRACKER_URL
    if "backtester_url" not in config["external_services"] or not config["external_services"]["backtester_url"]:
        config["external_services"]["backtester_url"] = DEFAULT_BACKTESTER_URL

    if "sorting" not in config:
        config["sorting"] = {}
    if "classification_priority" not in config["sorting"] or not config["sorting"]["classification_priority"]:
        config["sorting"]["classification_priority"] = DEFAULT_CLASSIFICATION_PRIORITY

    if "cron" not in config:
        config["cron"] = {}
    if "metrics_run_hour" not in config["cron"] or config["cron"]["metrics_run_hour"] is None:
        config["cron"]["metrics_run_hour"] = DEFAULT_METRICS_RUN_HOUR

    return config

def calculate_positions(tickers_map, tx_rows, div_rows, exchange_rates, portfolio_class_map=None, portfolio_broker_map=None, ib_positions=None):
    tx_by_key = defaultdict(list)
    for tx in tx_rows:
        pid = tx['portfolio_id']
        classification = portfolio_class_map.get(pid, 'Other') if portfolio_class_map else 'Other'
        tx_by_key[(tx['symbol'], classification)].append(tx)
        
    div_by_key = defaultdict(list)
    for div in div_rows:
        pid = div['portfolio_id']
        classification = portfolio_class_map.get(pid, 'Other') if portfolio_class_map else 'Other'
        div_by_key[(div['symbol'], classification)].append(div)
        
    positions_map = {}
    earliest_transaction_date = None
    
    keys = set(tx_by_key.keys()) | set(div_by_key.keys())
    
    for symbol, classification in keys:
        ticker_data = tickers_map.get(symbol)
        if not ticker_data:
            continue
            
        txs = tx_by_key.get((symbol, classification), [])
        divs = div_by_key.get((symbol, classification), [])
        
        currency = ticker_data['currency'] or 'USD'
        rate = exchange_rates.get(currency, 1.0)
        
        ticker_info = {
            'underlying': ticker_data['underlying'] or symbol,
            'classification': classification,
            'category': ticker_data.get('category') or ticker_data.get('subclass') or 'Other',
            'subclass': ticker_data.get('category') or ticker_data.get('subclass') or 'Other',
            'exchange': ticker_data.get('exchange')
        }
        
        pos = Position(symbol, ticker_info, rate)
        
        # Add transactions (chronologically) with split adjustment
        pos_tx_list = []
        for tx in txs:
            action = tx['action'].upper()
            date_only = tx['date'][:10]
            
            if earliest_transaction_date is None or date_only < earliest_transaction_date:
                earliest_transaction_date = date_only
                
            if action == 'SPLIT':
                ratio = tx['price']
                if ratio > 0:
                    for t in pos_tx_list:
                        t['qty'] *= ratio
                        t['price'] /= ratio
                pos_tx_list.append({
                    'action': 'Split',
                    'date': date_only,
                    'year': date_only[:4],
                    'qty': tx['quantity'],
                    'price': tx['price'],
                    'fee': tx['commission'] or 0.0,
                    'currency': tx['currency'],
                    'portfolio_id': tx['portfolio_id']
                })
            elif action in ('BUY', 'SELL'):
                pos_tx_list.append({
                    'action': action.capitalize(),
                    'date': date_only,
                    'year': date_only[:4],
                    'qty': tx['quantity'],
                    'price': tx['price'],
                    'fee': tx['commission'] or 0.0,
                    'currency': tx['currency'],
                    'portfolio_id': tx['portfolio_id']
                })
        
        for tx_item in pos_tx_list:
            pos.add_transaction(tx_item)
            
        # Add income
        for div in divs:
            date_only = div['date'][:10]
            
            if earliest_transaction_date is None or date_only < earliest_transaction_date:
                earliest_transaction_date = date_only
                
            qty = div.get('qty') or 0.0
            net_amt = div['amount'] - (div['tax'] or 0.0)
            
            pos.add_income({
                'action': 'Dividend',
                'date': date_only,
                'year': date_only[:4],
                'amt': div['amount'],
                'tax': div['tax'] or 0.0,
                'net': net_amt,
                'currency': div['currency'],
                'note': div['notes'] or '',
                'qty': qty,
                'gross_per_share': div['amount'] / qty if qty > 0 else 0.0,
                'net_per_share': net_amt / qty if qty > 0 else 0.0
            })
            
        # Set market value, daily change
        curr_qty = pos.current_quantity
        current_price = ticker_data['current_price'] or 0.0
        prev_close = ticker_data['prev_close'] or current_price
        
        pos.market_value = curr_qty * current_price
        pos.daily_val = curr_qty * (current_price - prev_close)
        pos.daily_pct = ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
        
        # Check reconciliation with IBKR data
        ibkr_calc_qty = 0.0
        for t in pos_tx_list:
            p_id = t.get('portfolio_id')
            if portfolio_broker_map and portfolio_broker_map.get(p_id) == 'IBKR':
                action = t['action']
                if action == 'Buy':
                    ibkr_calc_qty += t['qty']
                elif action == 'Sell':
                    ibkr_calc_qty -= t['qty']
                    
        is_augmented = False
        ib_mismatch = False
        ib_actual_qty = None
        if ib_positions and symbol in ib_positions:
            ib_actual_qty = ib_positions[symbol]["position"]
            if abs(ibkr_calc_qty - ib_actual_qty) < 0.0001:
                is_augmented = True
            else:
                ib_mismatch = True
                
        pos.is_augmented = is_augmented
        pos.ib_mismatch = ib_mismatch
        pos.ib_actual_qty = ib_actual_qty
        pos.ibkr_calc_qty = ibkr_calc_qty
        if is_augmented:
            pos.ib_cost_basis = ib_positions[symbol]["cost_basis"]
            pos.ib_unrealized_profits = ib_positions[symbol]["unrealized_profits"]
            pos.ib_market_value = ib_positions[symbol]["market_value"]
            pos.ib_current_price = ib_positions[symbol]["current_price"]
            
        positions_map[(symbol, classification)] = pos
        
    return list(positions_map.values()), earliest_transaction_date

def ingest_ibkr_cash_from_file(conn):
    """
    Read ib_data.json, extract balances, calculate the trading date and cumulative
    base capital for IBKR, and upsert the cash report to the daily_cash_report table.
    """
    config = load_config()
    ib_data_path = config.get("allowed_documents", {}).get("ib-data", "data/ib_data.json")
    if not os.path.exists(ib_data_path):
        logger.warning("[ingest_ibkr_cash] ib_data.json not found at %s. Skipping ingestion.", ib_data_path)
        return False

    try:
        with open(ib_data_path, 'r', encoding='utf-8') as f:
            ib_data = json.load(f)
        
        ib_balances = ib_data.get("balances", {})
        if not ib_balances:
            logger.warning("[ingest_ibkr_cash] No balances section in ib_data.json. Ingestion skipped.")
            return False
            
        trading_date = calculate_trading_date()
        
        cursor = conn.cursor()
        # Query base capital cumulative sum up to trading_date for IBKR
        cursor.execute("""
            SELECT SUM(amount) FROM broker_capital_entries 
            WHERE broker = 'IBKR' AND date <= ?
        """, (trading_date,))
        ibkr_base = cursor.fetchone()[0] or 0.0
        
        upsert_cash_report_in_db(
            conn, trading_date, "IBKR",
            float(ib_balances.get("NetLiquidation", 0.0)),
            ibkr_base,
            float(ib_balances.get("GrossPositionValue", 0.0)),
            float(ib_balances.get("TotalCashValue", 0.0))
        )
        logger.info("[ingest_ibkr_cash] Successfully ingested IBKR cash metrics for trading date %s from %s", trading_date, ib_data_path)
        return True
    except Exception as e:
        logger.error("[ingest_ibkr_cash] Failed to ingest cash report from %s: %s", ib_data_path, e)
        return False

def generate_views_in_memory(conn=None, price_mode="intraday", generate_mode="all"):
    """
    Query database, fetch options, perform calculations, and return rendered views as in-memory dict.
    """
    logger.info("[generate_views] Starting view generation (price_mode=%s)", price_mode)
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
        
    try:
        # Sync upcoming dividends with yfinance (cooldown-aware)
        from services.dividend_service import sync_upcoming_dividends
        try:
            sync_upcoming_dividends(conn, force=False)
        except Exception as e:
            logger.warning("Failed to sync upcoming dividends during view generation: %s", e)

        trading_date = calculate_trading_date()
        logger.info("[generate_views] Trading date: %s", trading_date)
        config = load_config()
        exchange_rates = get_exchange_rates()
        usd_rate = exchange_rates.get('USD', 1.0)
        
        # 1. First, update running cost basis and realized P&L for all portfolios
        logger.info("[generate_views] Updating cost basis and realized P&L for all portfolios...")
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM portfolios")
        portfolio_ids = [row['id'] for row in cursor.fetchall()]
        
        from core.calculations import calculate_holdings
        for pid in portfolio_ids:
            calculate_holdings(pid, conn)
            
        # 2. Query all tickers and price details based on price_mode
        logger.info("[generate_views] Querying tickers, transactions and dividends from DB...")
        # Intraday mode: daily change = intraday_current vs intraday_prev_close.
        # Closing mode:  daily change = daily_close vs daily_prev_close
        # (prevents 0% change while the market is still open today).
        price_col = "tp.daily_close" if price_mode == "closing" else "tp.intraday_current"
        prev_close_col = "COALESCE(tp.daily_prev_close, tp.intraday_prev_close)" if price_mode == "closing" else "tp.intraday_prev_close"
        cursor.execute(f"""
            SELECT t.id, t.symbol, t.friendly_name, t.underlying, t.category, t.tax_rate, t.exchange,
                   COALESCE({price_col}, tp.price) as current_price, {prev_close_col} as prev_close, tp.currency
            FROM tickers t
            LEFT JOIN ticker_prices tp ON t.id = tp.ticker_id
        """)
        tickers_rows = []
        for row in cursor.fetchall():
            d = dict(row)
            d['subclass'] = d.get('category') or 'Other'
            tickers_rows.append(d)
        tickers_map = {row['symbol']: row for row in tickers_rows}
        
        # 3. Query all transactions
        cursor.execute("""
            SELECT t.id, t.portfolio_id, t.ticker_id, t.date, t.action, t.price, t.quantity, 
                   t.currency, t.commission, t.cost_basis_after, t.realized_pl, t.realized_pl_sgd, t.notes,
                   tk.symbol
            FROM transactions t
            JOIN tickers tk ON t.ticker_id = tk.id
            ORDER BY t.date ASC, t.id ASC
        """)
        tx_rows = [dict(row) for row in cursor.fetchall()]
        
        # 4. Query all dividends
        cursor.execute("""
            SELECT d.id, d.portfolio_id, d.ticker_id, d.date, d.amount, d.currency, d.tax, d.notes, d.qty,
                   tk.symbol
            FROM dividends d
            JOIN tickers tk ON d.ticker_id = tk.id
            ORDER BY d.date ASC, d.id ASC
        """)
        div_rows = [dict(row) for row in cursor.fetchall()]
        
        # 8. Fetch portfolios list
        cursor.execute("SELECT id, name, classification, broker, sort_order FROM portfolios ORDER BY sort_order ASC, name ASC")
        portfolios = [dict(row) for row in cursor.fetchall()]
        portfolio_class_map = {p['id']: p['classification'] or p['name'] for p in portfolios}
        portfolio_broker_map = {p['id']: (p['broker'] or '').strip().upper() for p in portfolios}

        # Load ib_data.json if present
        ib_data_path = config.get("allowed_documents", {}).get("ib-data", "data/ib_data.json")
        ib_positions = {}
        ib_balances = {}
        if os.path.exists(ib_data_path):
            try:
                with open(ib_data_path, 'r', encoding='utf-8') as f:
                    ib_data = json.load(f)
                    ib_balances = ib_data.get("balances", {})
                    for pos in ib_data.get("portfolio", []):
                        sym = pos.get("symbol", "").replace(".", "-").upper()
                        ib_positions[sym] = {
                            "position": float(pos.get("position", 0.0) or 0.0),
                            "cost_basis": float(pos.get("cost_basis", 0.0) or 0.0),
                            "current_price": float(pos.get("current_price", 0.0) or 0.0),
                            "market_value": float(pos.get("market_value", 0.0) or 0.0),
                            "unrealized_profits": float(pos.get("unrealized_profits", 0.0) or 0.0),
                            "currency": pos.get("currency", "USD")
                        }
            except Exception as e:
                logger.warning("Failed to load ib_data.json: %s", e)

        # 5. Build Position objects
        logger.info("[generate_views] Building position objects from %d transactions, %d dividends...", len(tx_rows), len(div_rows))
        all_positions, earliest_transaction_date = calculate_positions(
            tickers_map, tx_rows, div_rows, exchange_rates,
            portfolio_class_map=portfolio_class_map,
            portfolio_broker_map=portfolio_broker_map,
            ib_positions=ib_positions
        )
        # 6 & 7. Fetch live options data and cash report details in parallel
        logger.info("[generate_views] Fetching options and cash report details in parallel...")
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_options = executor.submit(fetch_options_details, exchange_rates, trading_date=trading_date)
            future_cash = executor.submit(fetch_cash_report_details, earliest_transaction_date)
            
            options_data = future_options.result()
            cash_report_data = future_cash.result()

        # 9. Render all HTML and JSON views in memory
        logger.info("[generate_views] Rendering all views in memory...")
        result = render_all_views_in_memory(
            all_positions, options_data, cash_report_data, config, trading_date, 
            earliest_transaction_date, conn, portfolios, tickers_map, tx_rows, div_rows, exchange_rates, price_mode=price_mode,
            generate_mode=generate_mode
        )
        logger.info("[generate_views] View generation complete (price_mode=%s).", price_mode)
        return result
        
    finally:
        if close_conn:
            conn.close()

def rebuild_all_views(conn=None, price_mode="intraday", ingest_ibkr_cash=False):
    """
    Clears cache and ingests IBKR cash if requested.
    """
    logger.info("[rebuild_all_views] Clearing cache (price_mode=%s, ingest_ibkr_cash=%s)", price_mode, ingest_ibkr_cash)
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
        
    try:
        if ingest_ibkr_cash:
            ingest_ibkr_cash_from_file(conn)
        from core.cache import clear_dashboard_cache
        clear_dashboard_cache()
    finally:
        if close_conn:
            conn.close()
    return {}

def fetch_options_details(exchange_rates, trading_date=None):
    config = load_config()
    url = config.get("external_services", {}).get("options_tracker_url")
    if not url or not url.strip():
        return {
            "options_profit_sgd": 0.0,
            "total_open_max_loss_sgd": 0.0,
            "total_open_assignment_risk_sgd": 0.0,
            "total_open_potential_return_sgd": 0.0,
            "total_open_potential_return_pct": 0.0,
            "total_open_unrealized_profit_sgd": None,
            "total_open_unrealized_profit_pct": 0.0,
            "open_options": [],
            "recent_closed": None,
            "options_max_loss_breakdown": {},
            "ib_report_datetime_sgt": None,
            "options_daily_realized_sgd": 0.0
        }

    raw_data = None
    try:
        api_url = url
        if api_url and not api_url.endswith("/api/positions"):
            api_url = f"{api_url.rstrip('/')}/api/positions"
        response = requests.get(api_url, timeout=1)
        response.raise_for_status()
        raw_data = response.json()
    except Exception as e:
        logger.warning("Failed to fetch options tracker API: %s. Checking local file fallback.", e)
        config_path = config.get("allowed_documents", {}).get("stock-options", "data/stock-options.json")
        for path in [config_path]:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        raw_data = json.load(f)
                    break
                except:
                    pass
        if raw_data is None:
            raw_data = {"positions": [], "metadata": {}}
            
    ib_report_datetime_sgt = None
    all_options = []
    options_report_datetime_sgt = None
    
    if isinstance(raw_data, dict):
        all_options = raw_data.get('positions', [])
        ib_meta = raw_data.get('metadata', {})
        ib_dt_str = ib_meta.get('ib_report_datetime')
        if ib_dt_str:
            try:
                if ib_dt_str.endswith('Z'):
                    ib_dt_str = ib_dt_str[:-1] + '+00:00'
                dt_utc = datetime.fromisoformat(ib_dt_str)
                if dt_utc.tzinfo is None:
                    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                sgt_tz = timezone(timedelta(hours=8))
                dt_sgt = dt_utc.astimezone(sgt_tz)
                ib_report_datetime_sgt = dt_sgt.strftime("%Y-%m-%d %H:%M:%S SGT")
                options_report_datetime_sgt = ib_report_datetime_sgt
            except Exception as ex:
                logger.warning("Could not parse ib_report_datetime: %s", ex)
    else:
        all_options = raw_data
        
    usd_rate = exchange_rates.get('USD', 1.0)
    
    total_profit_usd = sum(
        item.get('realized_pnl_usd', 0.0) 
        for item in all_options 
        if item.get('status') == 'Closed'
    )
    options_profit_sgd = total_profit_usd * usd_rate
    
    open_groups_dict = {}
    total_open_max_loss_usd = 0.0
    total_open_assignment_risk_usd = 0.0
    
    today = datetime.now().date()
    
    for item in all_options:
        if item.get('status') == 'Open':
            item['total_cost_sgd'] = item.get('total_cost_usd', 0.0) * usd_rate
            item['max_loss_sgd'] = item.get('max_loss', 0.0) * usd_rate
            
            # Calculate Assignment Risk (Notional Exposure for Short Puts)
            if item.get('initial_type') == 'STO' and item.get('call_put') == 'Put':
                item_assignment_risk_usd = item.get('strike_price', 0.0) * item.get('multiplier', 100.0) * item.get('current_quantity', 1.0)
            else:
                item_assignment_risk_usd = 0.0
            item['assignment_risk_sgd'] = item_assignment_risk_usd * usd_rate
            
            if 'expiration_date' in item and item['expiration_date']:
                item['expiry_date'] = item['expiration_date'][:10]
            else:
                item['expiry_date'] = "N/A"
                
            group_id = item.get('group_id')
            if not group_id:
                group_id = f"single_{item.get('id')}"
                
            if group_id not in open_groups_dict:
                open_groups_dict[group_id] = {
                    "group_id": group_id,
                    "symbol": item.get("symbol"),
                    "expiry_date": item["expiry_date"],
                    "max_loss_usd": item.get('max_loss', 0.0),
                    "max_loss_sgd": item.get('max_loss', 0.0) * usd_rate,
                    "assignment_risk_usd": 0.0,
                    "assignment_risk_sgd": 0.0,
                    "total_cost_usd": 0.0,
                    "total_cost_sgd": 0.0,
                    "unrealized_profit_usd": 0.0,
                    "unrealized_profit_sgd": 0.0,
                    "legs": []
                }
                total_open_max_loss_usd += item.get('max_loss', 0.0)
                
            grp = open_groups_dict[group_id]
            grp["legs"].append(item)
            grp["total_cost_usd"] += item.get('total_cost_usd', 0.0)
            grp["total_cost_sgd"] += item['total_cost_sgd']
            grp["assignment_risk_usd"] += item_assignment_risk_usd
            grp["assignment_risk_sgd"] += item['assignment_risk_sgd']
            total_open_assignment_risk_usd += item_assignment_risk_usd
            
            unrealized_profit_usd = item.get('ib_unrealized_profits')
            if unrealized_profit_usd is not None:
                grp["unrealized_profit_usd"] += unrealized_profit_usd
                grp["unrealized_profit_sgd"] += unrealized_profit_usd * usd_rate
                
    for grp in open_groups_dict.values():
        cost = grp["total_cost_usd"]
        ml = grp["max_loss_usd"]
        if ml > 0 and cost > 0:
            grp["potential_return_pct"] = (cost / ml * 100)
        else:
            grp["potential_return_pct"] = 0
        
        # Compute individual option P/L percentage
        if grp["total_cost_usd"] != 0:
            grp["unrealized_profit_pct"] = (grp["unrealized_profit_usd"] / grp["total_cost_usd"] * 100)
        else:
            grp["unrealized_profit_pct"] = 0.0
        
        if grp["expiry_date"] != "N/A":
            try:
                expiry_dt = datetime.strptime(grp["expiry_date"], '%Y-%m-%d').date()
                grp["dte"] = (expiry_dt - today).days
            except:
                grp["dte"] = 0
        else:
            grp["dte"] = None
            
    total_open_max_loss_sgd = total_open_max_loss_usd * usd_rate
    total_open_assignment_risk_sgd = total_open_assignment_risk_usd * usd_rate
    
    total_open_potential_return_usd = sum(grp["total_cost_usd"] for grp in open_groups_dict.values())
    total_open_potential_return_sgd = total_open_potential_return_usd * usd_rate
    
    total_open_unrealized_profit_usd = sum(grp["unrealized_profit_usd"] for grp in open_groups_dict.values())
    total_open_unrealized_profit_sgd = total_open_unrealized_profit_usd * usd_rate
    
    if total_open_max_loss_sgd != 0:
        total_open_potential_return_pct = (total_open_potential_return_sgd / total_open_max_loss_sgd * 100)
    else:
        total_open_potential_return_pct = 0.0
        
    if total_open_potential_return_sgd != 0:
        total_open_unrealized_profit_pct = (total_open_unrealized_profit_sgd / total_open_potential_return_sgd * 100)
    else:
        total_open_unrealized_profit_pct = 0.0
        
    open_options = list(open_groups_dict.values())
    open_options.sort(key=lambda x: (x.get('expiry_date', '9999-12-31'), x['symbol']))
    
    # Group by expiration for breakdown
    max_loss_by_expiry = defaultdict(float)
    assignment_risk_by_expiry = defaultdict(float)
    for grp in open_options:
        if grp['expiry_date'] != "N/A":
            max_loss_by_expiry[grp['expiry_date']] += grp['max_loss_sgd']
            assignment_risk_by_expiry[grp['expiry_date']] += grp['assignment_risk_sgd']
            
    # Format breakdown with DTE
    options_max_loss_breakdown = []
    for expiry, ml_sgd in sorted(max_loss_by_expiry.items()):
        try:
            expiry_dt = datetime.strptime(expiry, '%Y-%m-%d').date()
            dte = (expiry_dt - today).days
        except:
            dte = 0
        options_max_loss_breakdown.append({
            "expiry_date": expiry,
            "dte": dte,
            "max_loss_sgd": ml_sgd,
            "assignment_risk_sgd": assignment_risk_by_expiry[expiry]
        })
        
    gen_at = datetime.now()
    start_date = gen_at - timedelta(weeks=4)
    weeks = defaultdict(lambda: {"groups": {}, "closed_pnl": 0, "closed_pnl_usd": 0})
    
    for pos in all_options:
        if pos['status'] == "Closed":
            closed_dt = None
            closing_tx = None
            for tx in sorted(pos.get('transactions', []), key=lambda x: x['date'], reverse=True):
                if tx['transaction_type'] in ['BTC', 'STC']:
                    closing_tx = tx
                    try:
                        closed_dt = datetime.fromisoformat(tx['date'].replace('Z', '+00:00'))
                    except:
                        closed_dt = datetime.strptime(tx['date'][:10], '%Y-%m-%d')
                    break
            
            if closed_dt:
                closed_dt_naive = closed_dt.replace(tzinfo=None)
                if closed_dt_naive >= start_date:
                    monday = closed_dt_naive - timedelta(days=closed_dt_naive.weekday())
                    week_key = monday.strftime('%Y-%m-%d')
                    pos['realized_pnl_sgd'] = pos.get('realized_pnl_usd', 0.0) * usd_rate
                    pos['date_closed'] = closed_dt_naive.strftime('%Y-%m-%d')
                    pos['action'] = closing_tx['transaction_type'] if closing_tx else pos.get('initial_type', '')
                    
                    try:
                        opened_dt = datetime.fromisoformat(pos['date_opened'].replace('Z', '+00:00')).replace(tzinfo=None)
                        pos['hold_days'] = (closed_dt_naive - opened_dt).days
                    except:
                        pos['hold_days'] = 0
                        
                    group_id = pos.get('group_id')
                    if not group_id:
                        group_id = f"closed_single_{pos.get('id')}"
                        
                    w = weeks[week_key]
                    if group_id not in w["groups"]:
                        w["groups"][group_id] = {
                            "group_id": group_id,
                            "symbol": pos.get("symbol"),
                            "date_closed": pos['date_closed'],
                            "realized_pnl_usd": 0.0,
                            "realized_pnl_sgd": 0.0,
                            "max_hold_days": 0,
                            "legs": []
                        }
                        
                    grp = w["groups"][group_id]
                    grp["legs"].append(pos)
                    grp["realized_pnl_usd"] += pos.get('realized_pnl_usd', 0.0)
                    grp["realized_pnl_sgd"] += pos['realized_pnl_sgd']
                    grp["max_hold_days"] = max(grp["max_hold_days"], pos['hold_days'])
                    
                    w["closed_pnl"] += pos['realized_pnl_sgd']
                    w["closed_pnl_usd"] += pos.get('realized_pnl_usd', 0.0)
                    
    sorted_weeks = []
    for week_start in sorted(weeks.keys(), reverse=True):
        w = weeks[week_start]
        monday_dt = datetime.strptime(week_start, '%Y-%m-%d')
        sunday_dt = monday_dt + timedelta(days=6)
        week_range = f"{monday_dt.strftime('%d %b')} - {sunday_dt.strftime('%d %b')}"
        closed_groups = list(w["groups"].values())
        closed_groups.sort(key=lambda x: x['date_closed'], reverse=True)
        
        sorted_weeks.append({
            "range": week_range,
            "closed": closed_groups,
            "closed_pnl": w["closed_pnl"],
            "closed_pnl_usd": w["closed_pnl_usd"]
        })
        
    recent_closed = {"weeks": sorted_weeks, "usd_rate": usd_rate} if sorted_weeks else None
    
    options_daily_realized_sgd = 0.0
    if trading_date:
        for pos in all_options:
            if pos.get('status') == 'Closed':
                closed_dt_str = None
                for tx in sorted(pos.get('transactions', []), key=lambda x: x['date'], reverse=True):
                    if tx['transaction_type'] in ['BTC', 'STC']:
                        closed_dt_str = tx['date'][:10]
                        break
                if closed_dt_str == trading_date:
                    options_daily_realized_sgd += pos.get('realized_pnl_usd', 0.0) * usd_rate

    return {
        "options_profit_sgd": options_profit_sgd,
        "total_open_max_loss_sgd": total_open_max_loss_sgd,
        "total_open_assignment_risk_sgd": total_open_assignment_risk_sgd,
        "total_open_potential_return_sgd": total_open_potential_return_sgd,
        "total_open_potential_return_pct": total_open_potential_return_pct,
        "total_open_unrealized_profit_sgd": total_open_unrealized_profit_sgd,
        "total_open_unrealized_profit_pct": total_open_unrealized_profit_pct,
        "open_options": open_options,
        "recent_closed": recent_closed,
        "options_max_loss_breakdown": options_max_loss_breakdown,
        "ib_report_datetime_sgt": ib_report_datetime_sgt,
        "options_daily_realized_sgd": options_daily_realized_sgd
    }


def fetch_cash_report_details(earliest_transaction_date):
    # Query the latest entries for both brokers from SQLite daily_cash_report
    from core.database import get_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Get cumulative base capital for each broker from broker_capital_entries
        cursor.execute("SELECT broker, SUM(amount) as base_capital FROM broker_capital_entries GROUP BY broker")
        base_cap_rows = cursor.fetchall()
        base_cap_map = {row['broker'].upper(): row['base_capital'] or 0.0 for row in base_cap_rows}
        
        # Query latest cash report row per broker
        cursor.execute("""
            SELECT r.broker, r.date, r.liquidation_value, r.total_stock_value, r.cash_on_hand, r.updated_at
            FROM daily_cash_report r
            INNER JOIN (
                SELECT broker, MAX(date) as max_date
                FROM daily_cash_report
                GROUP BY broker
            ) m ON r.broker = m.broker AND r.date = m.max_date
        """)
        rows = cursor.fetchall()
        if not rows:
            return None
            
        latest_records = [dict(row) for row in rows]
        
        # Sum details
        total_liq = 0.0
        total_cash = 0.0
        total_stock = 0.0
        total_base = 0.0
        details = {}
        
        last_updated_date = None
        last_updated_at = None
        for r in latest_records:
            br = r['broker'].upper()
            liq = r['liquidation_value'] or 0.0
            cash = r['cash_on_hand'] or 0.0
            stock = r['total_stock_value'] or 0.0
            
            # Get cumulative base capital for this broker up to this record's date
            cursor.execute("""
                SELECT SUM(amount) FROM broker_capital_entries 
                WHERE UPPER(broker) = ? AND date <= ?
            """, (br, r['date']))
            base = cursor.fetchone()[0] or 0.0
            
            total_liq += liq
            total_cash += cash
            total_stock += stock
            total_base += base
            
            gains = liq - base
            gains_pct = (gains / base * 100) if base != 0 else 0.0
            
            details[br.lower()] = {
                "liquidation_value": liq,
                "cash_on_hand": cash,
                "total_stock_value": stock,
                "base_capital": base,
                "base_capital_gains": gains,
                "base_capital_gains_pct": gains_pct
            }
            if not last_updated_date or r['date'] > last_updated_date:
                last_updated_date = r['date']
            # Track the most recent updated_at across all brokers
            row_updated_at = r['updated_at']
            if row_updated_at:
                if not last_updated_at or row_updated_at > last_updated_at:
                    last_updated_at = row_updated_at
                
        if not last_updated_date:
            last_updated_date = datetime.now().strftime("%Y-%m-%d")
        if not last_updated_at:
            last_updated_at = None
            
        total_gains = total_liq - total_base
        total_gains_pct = (total_gains / total_base * 100) if total_base != 0 else 0.0
        
        cash_report = {
            "liquidation_value": total_liq,
            "base_capital": total_base,
            "cash_on_hand": total_cash,
            "total_stock_value": total_stock,
            "base_capital_gains": total_gains,
            "base_capital_gains_pct": total_gains_pct,
            "last_updated_date": last_updated_date,
            "details": details
        }
        
        try:
            last_updated = datetime.strptime(last_updated_date[:10], "%Y-%m-%d")
        except:
            last_updated = datetime.now()
            
        if earliest_transaction_date:
            try:
                earliest_tx = datetime.strptime(earliest_transaction_date[:10], "%Y-%m-%d")
                days = (last_updated - earliest_tx).days
            except:
                days = 0
            cash_report['days_tracked'] = days
            if days > 0:
                cash_report['avg_returns_per_year'] = (total_gains_pct / days * 365)
            else:
                cash_report['avg_returns_per_year'] = 0
        else:
            cash_report['days_tracked'] = 0
            cash_report['avg_returns_per_year'] = 0
            
        # Build last_updated_formatted in SGT.
        # Prefer the precise updated_at UTC timestamp; fall back to trading date for legacy rows.
        SGT_OFFSET = 8 * 3600  # seconds
        from datetime import timezone, timedelta
        sgt_tz = timezone(timedelta(hours=8))
        if last_updated_at:
            try:
                dt_utc = datetime.strptime(last_updated_at, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                dt_sgt = dt_utc.astimezone(sgt_tz)
                cash_report['last_updated_formatted'] = dt_sgt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                cash_report['last_updated_formatted'] = last_updated.strftime("%Y-%m-%d")
        else:
            # Legacy rows without updated_at — just show the trading date
            cash_report['last_updated_formatted'] = last_updated.strftime("%Y-%m-%d")
        return cash_report
    except Exception as e:
        logger.warning("Error fetching cash report details: %s", e)
        return None
    finally:
        conn.close()

def render_all_views_in_memory(all_positions, options_data, cash_report_data, config, trading_date, earliest_transaction_date, conn, portfolios, tickers_map, tx_rows, div_rows, exchange_rates, price_mode="intraday", generate_mode="all"):
    portfolio_broker_map = {p['id']: (p['broker'] or '').strip().upper() for p in portfolios}

    # Load ib_data.json if present
    ib_data_path = config.get("allowed_documents", {}).get("ib-data", "data/ib_data.json")
    ib_positions = {}
    if os.path.exists(ib_data_path):
        try:
            with open(ib_data_path, 'r', encoding='utf-8') as f:
                ib_data = json.load(f)
                for pos in ib_data.get("portfolio", []):
                    sym = pos.get("symbol", "").replace(".", "-").upper()
                    ib_positions[sym] = {
                        "position": float(pos.get("position", 0.0) or 0.0),
                        "cost_basis": float(pos.get("cost_basis", 0.0) or 0.0),
                        "current_price": float(pos.get("current_price", 0.0) or 0.0),
                        "market_value": float(pos.get("market_value", 0.0) or 0.0),
                        "unrealized_profits": float(pos.get("unrealized_profits", 0.0) or 0.0),
                        "currency": pos.get("currency", "USD")
                    }
        except Exception as e:
            logger.warning("Failed to load ib_data.json: %s", e)

    suffix = f"_{price_mode}"
    views = {}
    
    # Fetch quotes last updated timestamp
    quotes_last_updated_sgt = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(last_updated) as max_updated FROM ticker_prices")
        max_row = cursor.fetchone()
        if max_row and max_row['max_updated']:
            dt_str = max_row['max_updated']
            import time
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                # Naive datetime from DB, assume system timezone
                tz_offset = -time.timezone if (time.localtime().tm_isdst == 0) else -time.altzone
                dt_utc = dt - timedelta(seconds=tz_offset)
                dt_sgt = dt_utc + timedelta(hours=8)
            else:
                dt_sgt = dt.astimezone(timezone(timedelta(hours=8)))
            quotes_last_updated_sgt = dt_sgt.strftime("%Y-%m-%d %H:%M:%S SGT")
    except Exception as ex:
        logger.warning("Failed to fetch quotes last updated timestamp: %s", ex)

    # Let's group all positions by classification
    positions_by_class = defaultdict(list)
    for p in all_positions:
        positions_by_class[p.classification].append(p)
        
    # Build the main portfolio_data.json ("All")
    main_daily_realized = sum(
        tx['realized_pl_sgd'] or 0.0 
        for tx in tx_rows 
        if tx['action'] == 'SELL' and tx['date'].startswith(trading_date)
    )
    explicit_classifications = {p['classification'] for p in portfolios if p['classification']}
    main_export = build_export_payload(
        all_positions, options_data, cash_report_data, config, 
        trading_date, earliest_transaction_date, classification_name="All", include_globals=True,
        quotes_last_updated_sgt=quotes_last_updated_sgt,
        daily_realized_pl_sgd=main_daily_realized,
        explicit_classifications=explicit_classifications
    )
    views["src/portfolio_data.json"] = main_export
    
    # Build specific category JSONs and metrics
    category_nav = []
    priority = config.get('sorting', {}).get('classification_priority', [])
    def class_sort_key(c_name):
        if not c_name or c_name == 'Other':
            return (999, 'Other')
        try:
            return (priority.index(c_name), c_name)
        except ValueError:
            return (100, c_name)
    unique_classes = sorted(list(set(p.classification for p in all_positions if p.classification in explicit_classifications)), key=class_sort_key)
    
    category_exports = {}
    for c_name in unique_classes:
        if c_name and c_name != "Other":
            slug = slugify(c_name)
            filename = f"portfolio_data_{slug}.json"
            c_pos = positions_by_class[c_name]
            
            cat_port_ids = {p['id'] for p in portfolios if (p['classification'] or p['name']) == c_name}
            cat_daily_realized = sum(
                tx['realized_pl_sgd'] or 0.0 
                for tx in tx_rows 
                if tx['portfolio_id'] in cat_port_ids and tx['action'] == 'SELL' and tx['date'].startswith(trading_date)
            )
            cat_export = build_export_payload(
                c_pos, options_data, cash_report_data, config,
                trading_date, earliest_transaction_date, classification_name=c_name, include_globals=False,
                quotes_last_updated_sgt=quotes_last_updated_sgt,
                daily_realized_pl_sgd=cat_daily_realized,
                explicit_classifications=explicit_classifications
            )
            views[f"src/{filename}"] = cat_export
            category_exports[slug] = cat_export
            
            category_nav.append({
                "name": c_name,
                "url": f"portfolio_active_{slug}.html",
                "id": f"pill-active-{slug}",
                "slug": slug
            })
            
    # Compile HTML files
    nav_items = [{"name": "All", "url": "portfolio_active.html", "id": "pill-active", "slug": "all"}]

    # Build per-portfolio nav and exports
    portfolio_nav = []
    portfolio_exports = {}  # slug -> export payload

    # Upsert global options profit metrics
    opt_profit = options_data.get("options_profit_sgd", 0.0)
    upsert_options_metrics_in_db(conn, trading_date, opt_profit)

    for port in portfolios:
        pid  = port['id']
        name = port['name']
        pslug = slugify(name)
        broker = port.get('broker') or ''

        # Filter transactions belonging only to this portfolio
        port_txs  = [tx  for tx  in tx_rows  if tx['portfolio_id']  == pid]
        port_divs = [div for div in div_rows if div['portfolio_id'] == pid]

        if not port_txs and not port_divs:
            continue  # skip portfolios with no activity

        port_class_map = {pid: port['classification'] or port['name']}
        port_positions, _ = calculate_positions(
            tickers_map, port_txs, port_divs, exchange_rates,
            portfolio_class_map=port_class_map,
            portfolio_broker_map=portfolio_broker_map,
            ib_positions=ib_positions
        )

        port_filename = f"portfolio_data_port_{pslug}.json"
        port_daily_realized = sum(
            tx['realized_pl_sgd'] or 0.0 
            for tx in tx_rows 
            if tx['portfolio_id'] == pid and tx['action'] == 'SELL' and tx['date'].startswith(trading_date)
        )
        port_export = build_export_payload(
            port_positions, options_data, cash_report_data, config,
            trading_date, earliest_transaction_date,
            classification_name=name, include_globals=False,
            quotes_last_updated_sgt=quotes_last_updated_sgt,
            daily_realized_pl_sgd=port_daily_realized
        )
        views[f"src/{port_filename}"] = port_export
        portfolio_exports[pslug] = port_export

        # Record daily portfolio metrics in db
        upsert_portfolio_metrics_in_db(
            conn, trading_date, pid,
            port_export["metadata"]["summary"]["total_invested_active_sgd"],
            port_export["metadata"]["summary"]["total_market_value_sgd"],
            port_export["metadata"]["summary"]["lifetime_profit_sgd"]
        )

        portfolio_nav.append({
            "name": name,
            "url": f"portfolio_active_port_{pslug}.html",
            "id": f"pill-active-port-{pslug}",
            "slug": f"port-{pslug}",
            "broker": broker,
        })

    # 2. Render Dividend Calendar JSON Data for SPA
    from services.dividend_calendar_service import DividendCalendarService
    try:
        div_gen = DividendCalendarService(main_export)
        _, cal_data = div_gen.generate(
            conn, exchange_rates,
            json_filename="dividend_calendar_data.json",
            category_nav=category_nav,
            port_nav=portfolio_nav
        )
        views["src/dividend_calendar_data.json"] = cal_data
    except Exception as e:
        logger.warning("Failed to render dividend calendar: %s", e)
        import traceback
        traceback.print_exc()

    return views

def build_export_payload(pos_list, options_data, cash_report_data, config, trading_date, earliest_transaction_date, classification_name, include_globals, quotes_last_updated_sgt=None, daily_realized_pl_sgd=0.0, explicit_classifications=None):
    active_pos = [p for p in pos_list if not p.is_closed]
    
    total_invested_sgd = sum(p.invested_sgd for p in active_pos)
    total_market_value_sgd = sum(p.current_sgd for p in active_pos)
    total_capital_gains_sgd = total_market_value_sgd - total_invested_sgd
    total_capital_gains_pct = (total_capital_gains_sgd / total_invested_sgd * 100) if total_invested_sgd != 0 else 0
    
    total_daily_sgd = sum(p.daily_val_sgd for p in active_pos)
    prev_total_market = total_market_value_sgd - total_daily_sgd
    total_daily_pct = (total_daily_sgd / prev_total_market * 100) if prev_total_market > 0 else 0
    
    if include_globals:
        options_profit_sgd = options_data["options_profit_sgd"]
        options_open_max_loss_sgd = options_data["total_open_max_loss_sgd"]
        options_assignment_risk_sgd = options_data["total_open_assignment_risk_sgd"]
        options_open_potential_return_sgd = options_data["total_open_potential_return_sgd"]
        options_open_potential_return_pct = options_data["total_open_potential_return_pct"]
        options_open_unrealized_profit_sgd = options_data["total_open_unrealized_profit_sgd"]
        options_open_unrealized_profit_pct = options_data["total_open_unrealized_profit_pct"]
        open_options_list = options_data["open_options"]
        recent_closed_options = options_data["recent_closed"]
        options_max_loss_breakdown = options_data["options_max_loss_breakdown"]
        options_report_datetime_sgt = options_data["ib_report_datetime_sgt"]
        cash_report = cash_report_data
    else:
        options_profit_sgd = 0.0
        options_open_max_loss_sgd = 0.0
        options_assignment_risk_sgd = 0.0
        options_open_potential_return_sgd = 0.0
        options_open_potential_return_pct = 0.0
        options_open_unrealized_profit_sgd = 0.0
        options_open_unrealized_profit_pct = 0.0
        open_options_list = []
        recent_closed_options = None
        options_max_loss_breakdown = []
        options_report_datetime_sgt = None
        cash_report = None
        
    realized_pnl_sgd = sum(p.realized_pnl_sgd for p in pos_list)
    dividends_net_sgd = sum(p.income_sgd for p in pos_list)
    dividends_gross_sgd = sum(sum(r['amt'] for r in p.income_records) * p.rate for p in pos_list)
    dividends_tax_sgd = sum(sum(r['tax'] for r in p.income_records) * p.rate for p in pos_list)
    fees_sgd = sum(p.fees_sgd for p in pos_list)
    lifetime_profit_sgd = sum(p.profit_sgd for p in pos_list) + options_profit_sgd
    
    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "generated_at_sgt": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S SGT"),
            "quotes_last_updated_sgt": quotes_last_updated_sgt,
            "ib_report_datetime_sgt": options_data["ib_report_datetime_sgt"] if include_globals else None,
            "options_report_datetime_sgt": options_report_datetime_sgt,
            "earliest_transaction": earliest_transaction_date,
            "config": config,
            "classification": classification_name,
            "trading_date": trading_date,
            "summary": {
                "total_invested_active_sgd": total_invested_sgd, 
                "total_market_value_sgd": total_market_value_sgd, 
                "total_capital_gains_sgd": total_capital_gains_sgd,
                "total_capital_gains_pct": total_capital_gains_pct,
                "total_realized_pnl_sgd": realized_pnl_sgd,
                "total_dividends_net_sgd": dividends_net_sgd,
                "total_dividends_gross_sgd": dividends_gross_sgd,
                "total_dividends_tax_sgd": dividends_tax_sgd,
                "total_fees_sgd": fees_sgd,
                "total_daily_sgd": total_daily_sgd,
                "total_daily_pct": total_daily_pct,
                "daily_realized_pl_sgd": daily_realized_pl_sgd,
                "options_profit_sgd": options_profit_sgd,
                "options_open_max_loss_sgd": options_open_max_loss_sgd,
                "options_assignment_risk_sgd": options_assignment_risk_sgd,
                "options_max_loss_by_expiry": options_max_loss_breakdown,
                "lifetime_profit_sgd": lifetime_profit_sgd,
                "options_open_potential_return_sgd": options_open_potential_return_sgd,
                "options_open_potential_return_pct": options_open_potential_return_pct,
                "options_open_unrealized_profit_sgd": options_open_unrealized_profit_sgd,
                "options_open_unrealized_profit_pct": options_open_unrealized_profit_pct,
                "options_daily_realized_sgd": options_data.get("options_daily_realized_sgd", 0.0) if include_globals else 0.0
            }

        },
        "dashboard": build_dashboard(active_pos, pos_list, config, explicit_classifications=explicit_classifications),
        "positions": [p.to_dict() for p in pos_list],
        "open_options": open_options_list,
        "recent_closed_options": recent_closed_options,
        "cash_report": cash_report
    }

def upsert_portfolio_metrics_in_db(conn, date_str, portfolio_id, total_invested, current_value, total_returns):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_portfolio_metrics (date, portfolio_id, total_invested, current_value, total_returns)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date, portfolio_id) DO UPDATE SET
            total_invested=excluded.total_invested,
            current_value=excluded.current_value,
            total_returns=excluded.total_returns
    """, (date_str, portfolio_id, total_invested, current_value, total_returns))
    conn.commit()

def upsert_options_metrics_in_db(conn, date_str, options_profit):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_options_metrics (date, options_profit)
        VALUES (?, ?)
        ON CONFLICT(date) DO UPDATE SET
            options_profit=excluded.options_profit
    """, (date_str, options_profit))
    conn.commit()

def upsert_cash_report_in_db(conn, date_str, broker, liquidation_value, base_capital, total_stock_value, cash_on_hand):
    from datetime import datetime, timezone
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_cash_report (date, broker, liquidation_value, base_capital, total_stock_value, cash_on_hand, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, broker) DO UPDATE SET
            liquidation_value=excluded.liquidation_value,
            base_capital=excluded.base_capital,
            total_stock_value=excluded.total_stock_value,
            cash_on_hand=excluded.cash_on_hand,
            updated_at=excluded.updated_at
    """, (date_str, broker.upper(), liquidation_value, base_capital, total_stock_value, cash_on_hand, updated_at))
    conn.commit()

if __name__ == "__main__":
    rebuild_all_views()
