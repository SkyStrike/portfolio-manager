import logging
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from fastapi import APIRouter, HTTPException
from core.database import get_connection
from services.fetch_exchange_rates import get_exchange_rates
from services.rebuild_dashboard import load_config

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/reports/options")
def get_options_report():
    logger.info("GET /api/reports/options")
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
            "ib_report_datetime_sgt": None
        }
    raw_data = None
    try:
        api_url = url
        if api_url and not api_url.endswith("/api/positions"):
            api_url = f"{api_url.rstrip('/')}/api/positions"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        raw_data = response.json()
    except Exception as e:
        logger.warning("Failed to fetch options tracker API: %s. Checking local file fallback.", e)
        for path in ["data/stock-options.json"]:
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
            except Exception as ex:
                logger.warning("Could not parse ib_report_datetime: %s", ex)
    else:
        all_options = raw_data
        
    rates = get_exchange_rates()
    usd_rate = rates.get('USD', 1.0)
    
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
    
    # Compute total potential return & unrealized profits for active options
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
        
    return {
        "options_profit_sgd": options_profit_sgd,
        "total_open_max_loss_sgd": total_open_max_loss_sgd,
        "total_open_assignment_risk_sgd": total_open_assignment_risk_sgd,
        "total_open_potential_return_sgd": total_open_potential_return_sgd,
        "total_open_potential_return_pct": total_open_potential_return_pct,
        "total_open_unrealized_profit_sgd": total_open_unrealized_profit_sgd,
        "total_open_unrealized_profit_pct": total_open_unrealized_profit_pct,
        "open_options": open_options,
        "recent_closed": sorted_weeks,
        "options_max_loss_breakdown": options_max_loss_breakdown,
        "ib_report_datetime_sgt": ib_report_datetime_sgt
    }

@router.get("/api/reports/performance")
def get_performance_report():
    from core.performance_calculator import get_performance_report_data
    import os
    db_path = os.getenv("PORTFOLIO_DB_FILE", "data/portfolio.db")
    data = get_performance_report_data(db_path)
    
    years = data["years"]
    classifications = data["classifications"]
    cash_by_year_month = data["cash_data"]
    portfolio_by_class_year_month = data["portfolio_data"]
    cash_ytd = data["cash_ytd"]
    portfolio_ytd = data["portfolio_ytd"]
    
    from services.performance_report_service import build_chart_data
    chart_data = build_chart_data(years, cash_by_year_month, portfolio_by_class_year_month, data.get("broker_cash_data"))
            
    return {
        "years": years,
        "classifications": sorted(list(classifications)),
        "cash_data": cash_by_year_month,
        "portfolio_data": portfolio_by_class_year_month,
        "cash_ytd": cash_ytd,
        "portfolio_ytd": dict(portfolio_ytd),
        "broker_cash_data": data.get("broker_cash_data", {}),
        "broker_cash_ytd": data.get("broker_cash_ytd", {}),
        "chart_data": chart_data
    }
