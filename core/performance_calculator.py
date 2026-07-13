import sqlite3
import os
from collections import defaultdict

def get_performance_report_data(db_path):
    """
    Connects to metrics.db, aggregates historical daily metrics by Year and Month,
    calculates MTD/MtM deltas, and structures it for Jinja2 template rendering.
    """
    if not os.path.exists(db_path):
        return {
            "years": [],
            "classifications": [],
            "cash_data": {},
            "portfolio_data": {}
        }
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch exchange rates to convert dividends
    cursor.execute("SELECT currency, rate FROM exchange_rates WHERE date = 'latest'")
    rates = {row['currency'].upper(): row['rate'] for row in cursor.fetchall()}
    rates['SGD'] = 1.0
    rates['USD'] = rates.get('USD', 1.34)  # Fallback if needed
    rates['CAD'] = rates.get('CAD', 1.0)
    
    def to_sgd(amount, currency):
        if not amount:
            return 0.0
        curr = (currency or 'SGD').strip().upper()
        if curr == 'SGD':
            return float(amount)
        rate = rates.get(curr, 1.0)
        return float(amount) * rate

    # 1. Fetch cash report records split by broker
    cursor.execute("SELECT date, broker, liquidation_value, total_stock_value, cash_on_hand FROM daily_cash_report ORDER BY date ASC")
    raw_cash_rows = [dict(row) for row in cursor.fetchall()]
    
    # Check for legacy cash report table to merge
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_cash_report_old'")
    has_old_table = bool(cursor.fetchone())
    
    new_report_dates = set(r['date'] for r in raw_cash_rows)
    
    if has_old_table:
        cursor.execute("SELECT date, 'CONSOLIDATED' as broker, liquidation_value, total_stock_value, cash_on_hand FROM daily_cash_report_old ORDER BY date ASC")
        old_rows = [dict(row) for row in cursor.fetchall() if row['date'] not in new_report_dates]
        raw_cash_rows.extend(old_rows)
        raw_cash_rows.sort(key=lambda x: x['date'])
        
    # Query capital entries to dynamically compute base capital
    cursor.execute("SELECT date, broker, amount FROM broker_capital_entries ORDER BY date ASC")
    capital_entries = [dict(row) for row in cursor.fetchall()]
    
    def get_base_capital_for_date(date_str, broker=None):
        if broker:
            br_upper = broker.upper()
            return sum(item['amount'] for item in capital_entries if item['date'] <= date_str and (item['broker'] or '').upper() == br_upper)
        else:
            return sum(item['amount'] for item in capital_entries if item['date'] <= date_str)
    
    # 2. Fetch portfolio records to map portfolio_id -> classification group AND portfolio name
    cursor.execute("SELECT id, name, classification, broker FROM portfolios")
    port_records = [dict(row) for row in cursor.fetchall()]
    port_map = {row['id']: (row['classification'] or row['name']) for row in port_records}
    port_name_map = {row['id']: row['name'] for row in port_records}
    
    # 3. Fetch portfolio metrics records
    cursor.execute("SELECT date, portfolio_id, total_invested, current_value, total_returns FROM daily_portfolio_metrics ORDER BY date ASC")
    raw_portfolio_rows = [dict(row) for row in cursor.fetchall()]
    
    # 4. Fetch global options metrics records
    cursor.execute("SELECT date, options_profit FROM daily_options_metrics ORDER BY date ASC")
    options_rows = {row['date']: row['options_profit'] for row in cursor.fetchall()}
    
    # 5. Fetch all dividends and pre-aggregate net dividends in SGD by month
    cursor.execute("""
        SELECT d.date, d.portfolio_id, d.amount, d.tax, d.currency, p.broker
        FROM dividends d
        JOIN portfolios p ON d.portfolio_id = p.id
    """)
    raw_dividend_rows = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # Aggregate net dividends in SGD by month
    global_dividends_by_month = defaultdict(float)
    broker_dividends_by_month = defaultdict(lambda: defaultdict(float))
    class_dividends_by_month = defaultdict(lambda: defaultdict(float))
    
    for d in raw_dividend_rows:
        dt = d['date']
        if not dt:
            continue
        month = dt[:7] # YYYY-MM
        pid = d['portfolio_id']
        net_sgd = to_sgd((d['amount'] or 0.0) - (d['tax'] or 0.0), d['currency'])
        
        global_dividends_by_month[month] += net_sgd
        
        br = (d['broker'] or '').strip().upper()
        if br:
            broker_dividends_by_month[br][month] += net_sgd
            
        cls = port_map.get(pid, 'Other')
        class_dividends_by_month[cls][month] += net_sgd
        
        pname = port_name_map.get(pid)
        if pname and pname != cls:
            class_dividends_by_month[pname][month] += net_sgd

    # Group raw cash rows by date using forward-filling to handle brokers on different dates
    active_brokers = sorted(list(set(r['broker'].upper() for r in raw_cash_rows if r['broker'].upper() != 'CONSOLIDATED')))
    unique_dates = sorted(list(set(r['date'] for r in raw_cash_rows)))
    
    latest_metrics = {
        br: {"liquidation_value": 0.0, "total_stock_value": 0.0, "cash_on_hand": 0.0}
        for br in active_brokers
    }
    
    rows_by_date_broker = {}
    for r in raw_cash_rows:
        rows_by_date_broker[(r['date'], r['broker'].upper())] = r
        
    cash_rows = []
    for dt in unique_dates:
        if (dt, 'CONSOLIDATED') in rows_by_date_broker:
            r = rows_by_date_broker[(dt, 'CONSOLIDATED')]
            consolidated = {
                "date": dt,
                "liquidation_value": r.get("liquidation_value") or 0.0,
                "base_capital": get_base_capital_for_date(dt),
                "total_stock_value": r.get("total_stock_value") or 0.0,
                "cash_on_hand": r.get("cash_on_hand") or 0.0
            }
        else:
            for br in active_brokers:
                if (dt, br) in rows_by_date_broker:
                    latest_metrics[br] = rows_by_date_broker[(dt, br)]
            
            consolidated = {
                "date": dt,
                "liquidation_value": sum(latest_metrics[br].get("liquidation_value") or 0.0 for br in active_brokers),
                "base_capital": get_base_capital_for_date(dt),
                "total_stock_value": sum(latest_metrics[br].get("total_stock_value") or 0.0 for br in active_brokers),
                "cash_on_hand": sum(latest_metrics[br].get("cash_on_hand") or 0.0 for br in active_brokers)
            }
        cash_rows.append(consolidated)
    
    # Group and aggregate portfolio metrics by date and classification/portfolio name on the fly
    aggregated_metrics = defaultdict(lambda: {"total_invested": 0.0, "current_value": 0.0, "total_returns": 0.0})
    classifications = set()
    
    for r in raw_portfolio_rows:
        pid = r['portfolio_id']
        cls = port_map.get(pid, 'Other')
        classifications.add(cls)
        
        key = (r['date'], cls)
        aggregated_metrics[key]["total_invested"] += r["total_invested"]
        aggregated_metrics[key]["current_value"] += r["current_value"]
        aggregated_metrics[key]["total_returns"] += r["total_returns"]
        
        pname = port_name_map.get(pid)
        if pname and pname != cls:
            classifications.add(pname)
            key_port = (r['date'], pname)
            aggregated_metrics[key_port]["total_invested"] += r["total_invested"]
            aggregated_metrics[key_port]["current_value"] += r["current_value"]
            aggregated_metrics[key_port]["total_returns"] += r["total_returns"]
        
    portfolio_rows = []
    for (date_str, cls), metrics in sorted(aggregated_metrics.items()):
        portfolio_rows.append({
            "date": date_str,
            "classification": cls,
            "total_invested": metrics["total_invested"],
            "current_value": metrics["current_value"],
            "options_profit": options_rows.get(date_str, 0.0),
            "total_returns": metrics["total_returns"]
        })
    
    # Group cash rows by month (YYYY-MM)
    cash_by_month = defaultdict(list)
    for r in cash_rows:
        month = r['date'][:7]
        cash_by_month[month].append(r)
        
    # Group portfolio rows by classification and month
    portfolio_by_class_month = defaultdict(lambda: defaultdict(list))
    for r in portfolio_rows:
        cls = r['classification']
        month = r['date'][:7]
        portfolio_by_class_month[cls][month].append(r)
        
    # Get all distinct years in chronological order
    all_months = sorted(list(set(list(cash_by_month.keys()) + [m for cls in portfolio_by_class_month for m in portfolio_by_class_month[cls]])))
    years = sorted(list(set(m[:4] for m in all_months)))
    
    # Helper to calculate delta and percentage change
    def get_change(curr, prev):
        if curr is None or prev is None:
            return None, None
        val = curr - prev
        pct = (val / prev * 100) if prev != 0 else 0.0
        return val, pct
 
    # Process Cash Report (Global Combined Net Worth)
    cash_summaries = {}
    sorted_cash_months = sorted(cash_by_month.keys())
    for idx, month in enumerate(sorted_cash_months):
        records = sorted(cash_by_month[month], key=lambda x: x['date'])
        r_first = records[0]
        r_last = records[-1]
        
        # Calculate Base Capital Gains dynamically
        first_base_cap = get_base_capital_for_date(r_first['date'])
        last_base_cap = get_base_capital_for_date(r_last['date'])
        
        r_first_gains = r_first['liquidation_value'] - first_base_cap
        r_last_gains = r_last['liquidation_value'] - last_base_cap
        
        r_prev_last = None
        r_prev_last_base_cap = 0.0
        if idx > 0:
            prev_month = sorted_cash_months[idx-1]
            prev_records = sorted(cash_by_month[prev_month], key=lambda x: x['date'])
            r_prev_last = prev_records[-1].copy()
            r_prev_last_base_cap = get_base_capital_for_date(r_prev_last['date'])
            r_prev_last['base_capital_gains'] = r_prev_last['liquidation_value'] - r_prev_last_base_cap
            
        r_base = r_prev_last if r_prev_last is not None else r_first
        r_base_base_cap = r_prev_last_base_cap if r_prev_last is not None else first_base_cap
        r_base_gains = r_base['liquidation_value'] - r_base_base_cap
        
        summary = {
            "month": month,
            "liquidation_value_start": r_base['liquidation_value'],
            "liquidation_value": r_last['liquidation_value'],
            "base_capital_start": r_base_base_cap,
            "base_capital": last_base_cap,
            "total_stock_value_start": r_base['total_stock_value'],
            "total_stock_value": r_last['total_stock_value'],
            "base_capital_gains_start": r_base_gains,
            "base_capital_gains": r_last_gains,
            "cash_on_hand_start": r_base['cash_on_hand'],
            "cash_on_hand": r_last['cash_on_hand'],
            "dividends_received": global_dividends_by_month.get(month, 0.0),
            "mtd": {},
            "mtm": {}
        }
        
        # Add base_capital_gains and base_capital helper dictionary overrides for delta calculations
        r_base_c = r_base.copy()
        r_base_c['base_capital'] = r_base_base_cap
        r_base_c['base_capital_gains'] = r_base_gains
        r_last_c = r_last.copy()
        r_last_c['base_capital'] = last_base_cap
        r_last_c['base_capital_gains'] = r_last_gains
        
        for key in ['liquidation_value', 'base_capital', 'total_stock_value', 'base_capital_gains', 'cash_on_hand']:
            summary["mtd"][f"{key}_val"], summary["mtd"][f"{key}_pct"] = get_change(r_last_c[key], r_base_c[key])
            if r_prev_last:
                r_prev_last_c = r_prev_last.copy()
                r_prev_last_c['base_capital'] = r_prev_last_base_cap
                summary["mtm"][f"{key}_val"], summary["mtm"][f"{key}_pct"] = get_change(r_last_c[key], r_prev_last_c[key])
            else:
                summary["mtm"][f"{key}_val"], summary["mtm"][f"{key}_pct"] = None, None
                
        cash_summaries[month] = summary
 
    # Process Portfolio metrics by classification
    portfolio_summaries = defaultdict(dict)
    for cls in classifications:
        cls_months = sorted(portfolio_by_class_month[cls].keys())
        for idx, month in enumerate(cls_months):
            records = sorted(portfolio_by_class_month[cls][month], key=lambda x: x['date'])
            r_first = records[0]
            r_last = records[-1]
            
            r_prev_last = None
            if idx > 0:
                prev_month = cls_months[idx-1]
                prev_records = sorted(portfolio_by_class_month[cls][prev_month], key=lambda x: x['date'])
                r_prev_last = prev_records[-1]
                
            r_base = r_prev_last if r_prev_last is not None else r_first
            
            summary = {
                "month": month,
                "total_invested_start": r_base['total_invested'],
                "total_invested": r_last['total_invested'],
                "current_value_start": r_base['current_value'],
                "current_value": r_last['current_value'],
                "options_profit_start": r_base.get('options_profit') if r_base.get('options_profit') is not None else 0.0,
                "options_profit": r_last.get('options_profit') if r_last.get('options_profit') is not None else 0.0,
                "total_returns_start": r_base['total_returns'],
                "total_returns": r_last['total_returns'],
                "dividends_received": class_dividends_by_month[cls].get(month, 0.0),
                "mtd": {},
                "mtm": {}
            }
            
            for key in ['total_invested', 'current_value', 'options_profit', 'total_returns']:
                base_val = r_base.get(key) if r_base.get(key) is not None else 0.0
                last_val = r_last.get(key) if r_last.get(key) is not None else 0.0
                summary["mtd"][f"{key}_val"], summary["mtd"][f"{key}_pct"] = get_change(last_val, base_val)
                
                if r_prev_last:
                    prev_val = r_prev_last.get(key) if r_prev_last.get(key) is not None else 0.0
                    summary["mtm"][f"{key}_val"], summary["mtm"][f"{key}_pct"] = get_change(last_val, prev_val)
                else:
                    summary["mtm"][f"{key}_val"], summary["mtm"][f"{key}_pct"] = None, None
                    
            portfolio_summaries[cls][month] = summary
            
    # Structure by Year (str) -> Month Index (1 to 12) -> summary data
    cash_by_year_month = defaultdict(dict)
    # Cash YTD
    cash_ytd = {}
    for y in years:
        y_months = sorted([m for m in cash_summaries if m.startswith(y)])
        if y_months:
            first_m_records = sorted(cash_by_month[y_months[0]], key=lambda x: x['date'])
            last_m_records = sorted(cash_by_month[y_months[-1]], key=lambda x: x['date'])
            r_first = first_m_records[0]
            r_last = last_m_records[-1]
            
            try:
                first_idx = cash_rows.index(r_first)
            except ValueError:
                first_idx = -1
                
            r_prev_year_last = None
            if first_idx > 0:
                r_prev_year_last = cash_rows[first_idx - 1].copy()
                
            r_base_ytd = r_prev_year_last if r_prev_year_last is not None else r_first
            
            base_cap_start = get_base_capital_for_date(r_base_ytd['date'])
            base_cap_end = get_base_capital_for_date(r_last['date'])
            
            gains_base = r_base_ytd['liquidation_value'] - base_cap_start
            gains_last = r_last['liquidation_value'] - base_cap_end
            
            liq_diff = r_last['liquidation_value'] - r_base_ytd['liquidation_value']
            cap_diff = base_cap_end - base_cap_start
            gains_diff = gains_last - gains_base
            
            cash_ytd[y] = {
                "liquidation_start": r_base_ytd['liquidation_value'],
                "liquidation_end": r_last['liquidation_value'],
                "liquidation_val": liq_diff,
                "liquidation_pct": (liq_diff / r_base_ytd['liquidation_value'] * 100) if r_base_ytd['liquidation_value'] > 0 else 0.0,
                "capital_start": base_cap_start,
                "capital_end": base_cap_end,
                "capital_val": cap_diff,
                "stock_start": r_base_ytd['total_stock_value'],
                "stock_end": r_last['total_stock_value'],
                "gains_start": gains_base,
                "gains_end": gains_last,
                "gains_val": gains_diff,
                "gains_pct": (gains_diff / base_cap_start * 100) if base_cap_start > 0 else 0.0,
                "cash_start": r_base_ytd['cash_on_hand'],
                "cash_end": r_last['cash_on_hand'],
                "dividends_received": sum(global_dividends_by_month.get(f"{y}-{str(m).zfill(2)}", 0.0) for m in range(1, 13))
            }
 
    # Portfolio YTD
    portfolio_ytd = defaultdict(dict)
    for cls in classifications:
        portfolio_rows_cls = sorted([r for r in portfolio_rows if r['classification'] == cls], key=lambda x: x['date'])
        for y in years:
            y_months = sorted([m for m in portfolio_summaries[cls] if m.startswith(y)])
            if y_months:
                first_m_records = sorted(portfolio_by_class_month[cls][y_months[0]], key=lambda x: x['date'])
                last_m_records = sorted(portfolio_by_class_month[cls][y_months[-1]], key=lambda x: x['date'])
                r_first = first_m_records[0]
                r_last = last_m_records[-1]
                
                try:
                    first_idx = portfolio_rows_cls.index(r_first)
                except ValueError:
                    first_idx = -1
                    
                r_prev_year_last = None
                if first_idx > 0:
                    r_prev_year_last = portfolio_rows_cls[first_idx - 1]
                    
                r_base_ytd = r_prev_year_last if r_prev_year_last is not None else r_first
                
                inv_diff = r_last['total_invested'] - r_base_ytd['total_invested']
                ret_diff = r_last['total_returns'] - r_base_ytd['total_returns']
                opt_diff = (r_last.get('options_profit') or 0.0) - (r_base_ytd.get('options_profit') or 0.0)
                
                portfolio_ytd[cls][y] = {
                    "invested_start": r_base_ytd['total_invested'],
                    "invested_end": r_last['total_invested'],
                    "invested_val": inv_diff,
                    "current_start": r_base_ytd['current_value'],
                    "current_end": r_last['current_value'],
                    "options_start": r_base_ytd.get('options_profit') or 0.0,
                    "options_end": r_last.get('options_profit') or 0.0,
                    "options_val": opt_diff,
                    "returns_start": r_base_ytd['total_returns'],
                    "returns_end": r_last['total_returns'],
                    "returns_val": ret_diff,
                    "returns_pct": (ret_diff / r_base_ytd['total_invested'] * 100) if r_base_ytd['total_invested'] > 0 else 0.0,
                    "dividends_received": sum(class_dividends_by_month[cls].get(f"{y}-{str(m).zfill(2)}", 0.0) for m in range(1, 13))
                }
 
    # Structure by Year (str) -> Month Index (1 to 12) -> summary data
    cash_by_year_month = defaultdict(dict)
    for month_str, summary in cash_summaries.items():
        y = month_str[:4]
        m_idx = int(month_str[5:7])
        cash_by_year_month[y][m_idx] = summary
        
    portfolio_by_class_year_month = defaultdict(lambda: defaultdict(dict))
    for cls in classifications:
        for month_str, summary in portfolio_summaries[cls].items():
            y = month_str[:4]
            m_idx = int(month_str[5:7])
            portfolio_by_class_year_month[cls][y][m_idx] = summary
            
    # Calculate separate YTD and monthly metrics for each broker
    # Group raw cash rows by broker and month
    broker_cash_by_month = defaultdict(lambda: defaultdict(list))
    for r in raw_cash_rows:
        br = r['broker'].upper()
        if br == 'CONSOLIDATED':
            continue
        month = r['date'][:7]
        broker_cash_by_month[br][month].append(r)
        
    broker_cash_summaries = defaultdict(dict)
    broker_cash_ytd = defaultdict(dict)
    
    for br, br_months_data in broker_cash_by_month.items():
        broker_rows = sorted([r for month in br_months_data for r in br_months_data[month]], key=lambda x: x['date'])
        sorted_br_months = sorted(br_months_data.keys())
        for idx, month in enumerate(sorted_br_months):
            records = sorted(br_months_data[month], key=lambda x: x['date'])
            r_first = records[0]
            r_last = records[-1]
            
            first_base_cap = get_base_capital_for_date(r_first['date'], broker=br)
            last_base_cap = get_base_capital_for_date(r_last['date'], broker=br)
            
            r_first_gains = r_first['liquidation_value'] - first_base_cap
            r_last_gains = r_last['liquidation_value'] - last_base_cap
            
            r_prev_last = None
            r_prev_last_base_cap = 0.0
            if idx > 0:
                prev_month = sorted_br_months[idx-1]
                prev_records = sorted(br_months_data[prev_month], key=lambda x: x['date'])
                r_prev_last = prev_records[-1].copy()
                r_prev_last_base_cap = get_base_capital_for_date(r_prev_last['date'], broker=br)
                r_prev_last['base_capital_gains'] = r_prev_last['liquidation_value'] - r_prev_last_base_cap
                
            r_base = r_prev_last if r_prev_last is not None else r_first
            r_base_base_cap = r_prev_last_base_cap if r_prev_last is not None else first_base_cap
            r_base_gains = r_base['liquidation_value'] - r_base_base_cap
            
            summary = {
                "month": month,
                "liquidation_value_start": r_base['liquidation_value'],
                "liquidation_value": r_last['liquidation_value'],
                "base_capital_start": r_base_base_cap,
                "base_capital": last_base_cap,
                "total_stock_value_start": r_base['total_stock_value'],
                "total_stock_value": r_last['total_stock_value'],
                "base_capital_gains_start": r_base_gains,
                "base_capital_gains": r_last_gains,
                "cash_on_hand_start": r_base['cash_on_hand'],
                "cash_on_hand": r_last['cash_on_hand'],
                "dividends_received": broker_dividends_by_month[br].get(month, 0.0),
                "mtd": {},
                "mtm": {}
            }
            
            # Add base_capital_gains and base_capital helper dictionary overrides for delta calculations
            r_base_c = r_base.copy()
            r_base_c['base_capital'] = r_base_base_cap
            r_base_c['base_capital_gains'] = r_base_gains
            r_last_c = r_last.copy()
            r_last_c['base_capital'] = last_base_cap
            r_last_c['base_capital_gains'] = r_last_gains
            
            for key in ['liquidation_value', 'base_capital', 'total_stock_value', 'base_capital_gains', 'cash_on_hand']:
                summary["mtd"][f"{key}_val"], summary["mtd"][f"{key}_pct"] = get_change(r_last_c[key], r_base_c[key])
                if r_prev_last:
                    r_prev_last_c = r_prev_last.copy()
                    r_prev_last_c['base_capital'] = r_prev_last_base_cap
                    summary["mtm"][f"{key}_val"], summary["mtm"][f"{key}_pct"] = get_change(r_last_c[key], r_prev_last_c[key])
                else:
                    summary["mtm"][f"{key}_val"], summary["mtm"][f"{key}_pct"] = None, None
                    
            y = month[:4]
            m_idx = int(month[5:7])
            if y not in broker_cash_summaries[br]:
                broker_cash_summaries[br][y] = {}
            broker_cash_summaries[br][y][m_idx] = summary
            
        # Broker Cash YTD
        for y in years:
            y_months = sorted([m for m in br_months_data if m.startswith(y)])
            if y_months:
                first_m_records = sorted(br_months_data[y_months[0]], key=lambda x: x['date'])
                last_m_records = sorted(br_months_data[y_months[-1]], key=lambda x: x['date'])
                r_first = first_m_records[0]
                r_last = last_m_records[-1]
                
                try:
                    first_idx = broker_rows.index(r_first)
                except ValueError:
                    first_idx = -1
                    
                r_prev_year_last = None
                if first_idx > 0:
                    r_prev_year_last = broker_rows[first_idx - 1]
                    
                r_base_ytd = r_prev_year_last if r_prev_year_last is not None else r_first
                
                base_cap_start = get_base_capital_for_date(r_base_ytd['date'], broker=br)
                base_cap_end = get_base_capital_for_date(r_last['date'], broker=br)
                
                gains_base = r_base_ytd['liquidation_value'] - base_cap_start
                gains_last = r_last['liquidation_value'] - base_cap_end
                
                liq_diff = r_last['liquidation_value'] - r_base_ytd['liquidation_value']
                cap_diff = base_cap_end - base_cap_start
                gains_diff = gains_last - gains_base
                
                broker_cash_ytd[br][y] = {
                    "liquidation_start": r_base_ytd['liquidation_value'],
                    "liquidation_end": r_last['liquidation_value'],
                    "liquidation_val": liq_diff,
                    "liquidation_pct": (liq_diff / r_base_ytd['liquidation_value'] * 100) if r_base_ytd['liquidation_value'] > 0 else 0.0,
                    "capital_start": base_cap_start,
                    "capital_end": base_cap_end,
                    "capital_val": cap_diff,
                    "stock_start": r_base_ytd['total_stock_value'],
                    "stock_end": r_last['total_stock_value'],
                    "gains_start": gains_base,
                    "gains_end": gains_last,
                    "gains_val": gains_diff,
                    "gains_pct": (gains_diff / base_cap_start * 100) if base_cap_start > 0 else 0.0,
                    "cash_start": r_base_ytd['cash_on_hand'],
                    "cash_end": r_last['cash_on_hand'],
                    "dividends_received": sum(broker_dividends_by_month[br].get(f"{y}-{str(m).zfill(2)}", 0.0) for m in range(1, 13))
                }
            
    return {
        "years": years,
        "classifications": sorted(list(classifications)),
        "cash_data": cash_by_year_month,
        "portfolio_data": portfolio_by_class_year_month,
        "cash_ytd": cash_ytd,
        "portfolio_ytd": dict(portfolio_ytd),
        "broker_cash_data": dict(broker_cash_summaries),
        "broker_cash_ytd": dict(broker_cash_ytd)
    }
