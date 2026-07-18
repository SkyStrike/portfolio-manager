import json
import os
import datetime
from datetime import timedelta
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader

def commas(value, precision=2, sign=False):
    if value is None: return "0.00"
    fmt = f"{{:,.{precision}f}}"
    if sign and value > 0: fmt = "+" + fmt
    return fmt.format(value)

class DividendCalendarGenerator:
    def __init__(self, data_or_path, template_dir='templates'):
        if isinstance(data_or_path, dict):
            self.data = data_or_path
        else:
            with open(data_or_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True
        )
        self.env.filters['commas'] = commas
        
        # Setup BASE_PATH global helper
        from core.cache import base_path
        self.env.globals['BASE_PATH'] = base_path

    def calculate_suppression_and_frequency(self, conn):
        """
        Dynamically calculates the suppression window (in days) and payout frequency for each ticker
        based on the frequency of its upcoming dividends.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT ticker_id, ex_date FROM upcoming_dividends ORDER BY ticker_id, ex_date ASC")
        rows = cursor.fetchall()
        
        ticker_dates = defaultdict(list)
        for r in rows:
            try:
                dt = datetime.datetime.strptime(r["ex_date"][:10], "%Y-%m-%d").date()
                ticker_dates[r["ticker_id"]].append(dt)
            except ValueError:
                pass
                
        info = {}
        for ticker_id, dates in ticker_dates.items():
            if len(dates) < 2:
                # Try historical dividends count to guess frequency
                cursor.execute("""
                    SELECT date FROM dividends 
                    WHERE ticker_id = ? 
                    ORDER BY date ASC
                """, (ticker_id,))
                hist_rows = cursor.fetchall()
                hist_dates = []
                for hr in hist_rows:
                    try:
                        hist_dates.append(datetime.datetime.strptime(hr["date"][:10], "%Y-%m-%d").date())
                    except ValueError:
                        pass
                
                if len(hist_dates) >= 2:
                    dates = hist_dates
                else:
                    info[ticker_id] = {"window": 15, "frequency": 4} # Default
                    continue
                    
            # Calculate minimum gap
            min_gap = 9999
            for i in range(1, len(dates)):
                gap = (dates[i] - dates[i-1]).days
                if 0 < gap < min_gap:
                    min_gap = gap
                    
            if min_gap <= 10:
                info[ticker_id] = {"window": 3, "frequency": 52}   # Weekly
            elif 15 <= min_gap <= 40:
                info[ticker_id] = {"window": 10, "frequency": 12}  # Monthly
            elif 70 <= min_gap <= 110:
                info[ticker_id] = {"window": 15, "frequency": 4}   # Quarterly
            elif 150 <= min_gap <= 210:
                info[ticker_id] = {"window": 15, "frequency": 2}   # Semi-Annually
            else:
                info[ticker_id] = {"window": 15, "frequency": 1}   # Annually
                
        return info

    def generate_calendar_data(self, conn, exchange_rates):
        cursor = conn.cursor()
        
        # 1. Fetch ticker metadata (tax_rate, friendly_name, yield)
        cursor.execute("""
            SELECT t.id, t.symbol, t.friendly_name, t.tax_rate,
                   COALESCE(tp.intraday_prev_close, 0.0) as prev_close,
                   COALESCE(tp.intraday_current, tp.price, 0.0) as price,
                   tp.currency
            FROM tickers t
            LEFT JOIN ticker_prices tp ON t.id = tp.ticker_id
        """)
        tickers_info = {r["id"]: dict(r) for r in cursor.fetchall()}
        symbol_to_id = {r["symbol"]: r["id"] for r in tickers_info.values()}
        
        # 2. Get active shares per portfolio and ticker_id
        cursor.execute("""
            SELECT portfolio_id, ticker_id,
                   SUM(CASE WHEN action = 'BUY' THEN quantity WHEN action = 'SELL' THEN -quantity ELSE 0 END) as shares
            FROM transactions
            GROUP BY portfolio_id, ticker_id
            HAVING SUM(CASE WHEN action = 'BUY' THEN quantity WHEN action = 'SELL' THEN -quantity ELSE 0 END) > 0.0001
        """)
        active_shares = [dict(row) for row in cursor.fetchall()]
        
        # Mapping of (portfolio_id, ticker_id) -> active shares quantity
        active_map = {(r["portfolio_id"], r["ticker_id"]): r["shares"] for r in active_shares}
        active_ticker_ids = {r["ticker_id"] for r in active_shares}
        
        # 3. Fetch Paid dividends
        cursor.execute("""
            SELECT d.id, d.portfolio_id, d.ticker_id, d.date, d.amount, d.currency, d.tax, d.notes,
                   p.name as portfolio_name
            FROM dividends d
            JOIN portfolios p ON d.portfolio_id = p.id
        """)
        paid_rows = [dict(row) for row in cursor.fetchall()]
        
        # 4. Fetch upcoming dividends
        cursor.execute("""
            SELECT id, ticker_id, ex_date, payment_date, amount, currency, status 
            FROM upcoming_dividends
        """)
        upcoming_rows = [dict(row) for row in cursor.fetchall()]
        
        # 5. Fetch dynamic suppression windows and frequencies
        ticker_calendar_info = self.calculate_suppression_and_frequency(conn)
        
        # 6. Pre-calculate transaction histories to track cost basis / shares at any date
        cursor.execute("""
            SELECT portfolio_id, ticker_id, date, action, quantity, cost_basis_after
            FROM transactions
            ORDER BY date ASC, id ASC
        """)
        all_txs = cursor.fetchall()
        
        holdings_history = defaultdict(list)
        running_state = {} # (pid, tid) -> {"shares": 0.0, "avg_cost": 0.0}
        
        for tx in all_txs:
            pid = tx["portfolio_id"]
            tid = tx["ticker_id"]
            date_str = tx["date"][:10]
            action = tx["action"].upper()
            qty = tx["quantity"]
            cost_after = tx["cost_basis_after"] or 0.0
            
            key = (pid, tid)
            if key not in running_state:
                running_state[key] = {"shares": 0.0, "avg_cost": 0.0}
                
            state = running_state[key]
            if action == "BUY":
                state["shares"] += qty
                state["avg_cost"] = cost_after
            elif action == "SELL":
                state["shares"] -= qty
                state["avg_cost"] = cost_after
                if state["shares"] <= 0.0001:
                    state["shares"] = 0.0
                    state["avg_cost"] = 0.0
            
            holdings_history[key].append((date_str, state["shares"], state["avg_cost"]))
            
        def get_holdings_at_date(pid, tid, date_str):
            history = holdings_history.get((pid, tid))
            if not history:
                return 0.0, 0.0
            
            last_shares = 0.0
            last_avg_cost = 0.0
            for h_date, h_shares, h_avg_cost in history:
                if h_date <= date_str:
                    last_shares = h_shares
                    last_avg_cost = h_avg_cost
                else:
                    break
            return last_shares, last_avg_cost
            
        # Consolidated calendar items
        calendar_items = []
        
        # A. Process Paid dividends (historical)
        for p in paid_rows:
            date_str = p["date"][:10]
            try:
                pay_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
                
            tk_id = p["ticker_id"]
            tk_meta = tickers_info.get(tk_id, {})
            symbol = tk_meta.get("symbol", f"T{tk_id}")
            friendly_name = tk_meta.get("friendly_name") or symbol
            
            # Exchange rate
            rate = exchange_rates.get(p["currency"], 1.0)
            net_foreign = p["amount"] - p["tax"]
            net_sgd = net_foreign * rate
            
            # Resolve frequency & cost basis at payout date for yield calculation
            freq_info = ticker_calendar_info.get(tk_id, {"window": 15, "frequency": 4})
            frequency = freq_info["frequency"]
            
            shares_at_date, avg_cost_at_date = get_holdings_at_date(p["portfolio_id"], tk_id, date_str)
            total_invested = shares_at_date * avg_cost_at_date
            
            # Gross is total gross payout. Derive amount per share: gross / shares (if shares > 0)
            amount_per_share = p["amount"] / shares_at_date if shares_at_date > 0 else p["amount"]
            
            yield_pct = 0.0
            if total_invested > 0:
                # Estimated Yield: gross * frequency / total_invested * 100
                yield_pct = (p["amount"] * frequency / total_invested * 100)
            
            calendar_items.append({
                "id": f"paid-{p['id']}",
                "portfolio_id": p["portfolio_id"],
                "portfolio_name": p["portfolio_name"],
                "ticker_id": tk_id,
                "ticker": symbol,
                "friendly_name": friendly_name,
                "date": date_str,
                "gross_amount": p["amount"],
                "net_amount_foreign": net_foreign,
                "net_amount_sgd": net_sgd,
                "currency": p["currency"],
                "status": "Paid",
                "yield_pct": round(yield_pct, 2),
                "shares": shares_at_date,
                "amount_per_share": amount_per_share
            })
            
        # B. Process Declared & Estimated dividends (with suppression check)
        for u in upcoming_rows:
            tk_id = u["ticker_id"]
            # Only generate for active holdings
            if tk_id not in active_ticker_ids:
                continue
                
            tk_meta = tickers_info.get(tk_id, {})
            symbol = tk_meta.get("symbol", f"T{tk_id}")
            friendly_name = tk_meta.get("friendly_name") or symbol
            tax_rate = tk_meta.get("tax_rate") or 0.0
            
            pay_date_str = u["payment_date"][:10]
            try:
                pay_dt = datetime.datetime.strptime(pay_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
                
            # Suppression window & frequency
            freq_info = ticker_calendar_info.get(tk_id, {"window": 15, "frequency": 4})
            window_days = freq_info["window"]
            frequency = freq_info["frequency"]
            
            # For each portfolio holding this ticker, check if a Paid dividend exists in matching window
            for (pid, active_tk_id), shares in active_map.items():
                if active_tk_id != tk_id:
                    continue
                    
                # Suppression check
                suppressed = False
                for p_item in calendar_items:
                    if (p_item["status"] == "Paid" and 
                        p_item["portfolio_id"] == pid and 
                        p_item["ticker_id"] == tk_id):
                        p_date = datetime.datetime.strptime(p_item["date"], "%Y-%m-%d").date()
                        if abs((pay_dt - p_date).days) <= window_days:
                            suppressed = True
                            break
                            
                if suppressed:
                    continue
                    
                # Fetch portfolio name
                cursor.execute("SELECT name FROM portfolios WHERE id = ?", (pid,))
                p_row = cursor.fetchone()
                portfolio_name = p_row["name"] if p_row else "Unknown"
                
                # Calculations
                gross_amount = shares * u["amount"]
                net_foreign = gross_amount * (1.0 - tax_rate)
                rate = exchange_rates.get(u["currency"], 1.0)
                net_sgd = net_foreign * rate
                
                # Yield calculations: (dividend_per_share * frequency / avg_cost) * 100
                # Using date "9999-12-31" to fetch the latest current average cost of position
                _, avg_cost = get_holdings_at_date(pid, tk_id, "9999-12-31")
                
                yield_pct = 0.0
                if avg_cost > 0:
                    yield_pct = (u["amount"] * frequency / avg_cost * 100)
                
                calendar_items.append({
                    "id": f"upcoming-{u['id']}-{pid}",
                    "portfolio_id": pid,
                    "portfolio_name": portfolio_name,
                    "ticker_id": tk_id,
                    "ticker": symbol,
                    "friendly_name": friendly_name,
                    "date": pay_date_str,
                    "gross_amount": gross_amount,
                    "net_amount_foreign": net_foreign,
                    "net_amount_sgd": net_sgd,
                    "currency": u["currency"],
                    "status": u["status"],
                    "yield_pct": round(yield_pct, 2),
                    "shares": shares,
                    "amount_per_share": u["amount"]
                })
                
        # 6. Aggregate monthly totals for next 12 months chart
        # Next 12 months forward breakdown starting from today
        today = datetime.date.today()
        month_keys = []
        for i in range(12):
            m = today.month + i
            y = today.year
            while m > 12:
                m -= 12
                y += 1
            month_keys.append(f"{y:04d}-{m:02d}")
            
        chart_breakdown = {k: {"Paid": 0.0, "Declared": 0.0, "Estimated": 0.0} for k in month_keys}
        
        # Calculate Next 12-month Annual expected income
        annual_income_sgd = 0.0
        yet_to_receive_sgd = 0.0
        
        for item in calendar_items:
            m_key = item["date"][:7]
            # Sum for active next-12-months chart
            if m_key in chart_breakdown:
                chart_breakdown[m_key][item["status"]] += item["net_amount_sgd"]
                annual_income_sgd += item["net_amount_sgd"]
                
                if item["status"] in ("Declared", "Estimated"):
                    yet_to_receive_sgd += item["net_amount_sgd"]
                    
        # Total portfolio market value for yield calculation
        total_market_value_sgd = self.data["metadata"]["summary"].get("total_market_value_sgd", 1.0)
        portfolio_yield = (annual_income_sgd / total_market_value_sgd * 100) if total_market_value_sgd > 0 else 0.0
        
        # Month labels helper for ApexCharts / Chart.js
        months_short = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        chart_labels = []
        chart_paid = []
        chart_declared = []
        chart_estimated = []
        
        for m_key in month_keys:
            y, m = m_key.split("-")
            label = f"{months_short[int(m)-1]} {y[2:]}"
            chart_labels.append(label)
            chart_paid.append(round(chart_breakdown[m_key]["Paid"], 2))
            chart_declared.append(round(chart_breakdown[m_key]["Declared"], 2))
            chart_estimated.append(round(chart_breakdown[m_key]["Estimated"], 2))
            
        # Clean sort calendar items chronologically
        calendar_items.sort(key=lambda x: x["date"])
        
        return {
            "summary": {
                "annual_income_sgd": round(annual_income_sgd, 2),
                "monthly_average_sgd": round(annual_income_sgd / 12, 2),
                "daily_average_sgd": round(annual_income_sgd / 365, 2),
                "portfolio_yield_pct": round(portfolio_yield, 2),
                "yet_to_receive_sgd": round(yet_to_receive_sgd, 2)
            },
            "chart": {
                "labels": chart_labels,
                "paid": chart_paid,
                "declared": chart_declared,
                "estimated": chart_estimated
            },
            "items": calendar_items
        }

    def generate(self, conn, exchange_rates, json_filename="portfolio_data.json", category_nav=None, port_nav=None):
        cal_data = self.generate_calendar_data(conn, exchange_rates)
        
        # 1. Render content (dividend_calendar.html)
        content_template = self.env.get_template('dividend_calendar.html')
        content_rendered = content_template.render(
            cal=cal_data,
            meta=self.data["metadata"],
            JSON_FILENAME=json_filename
        )
        
        # 2. Render css/js dependencies
        from services.css_helper import render_combined_css
        ui_config = self.data.get('metadata', {}).get('config', {}).get('ui', {})
        page_width = ui_config.get('page_width', '1800px')
        css_rendered = render_combined_css(self.env, page_width=page_width, chart_height="40vh")
        
        js_template = self.env.get_template('scripts.js')
        js_rendered = js_template.render(
            COLOR_INVESTED='#8b5cf6', 
            COLOR_CURRENT='#3498db',
            COLOR_RETURNS='#2ecc71',
            COLOR_INCOME='#2ecc71',
            COLOR_POSITIVE='#3498db',
            COLOR_NEGATIVE='#e74c3c',
            UI_FONT_SIZE=ui_config.get('font_size', '14px'),
            UI_MOBILE_FONT_SIZE=ui_config.get('mobile_font_size', '12px')
        )
        
        # 3. Resolve configs for base
        from services.rebuild_dashboard import load_config
        config = load_config()
        allowed_docs = config.get("allowed_documents", {})
        ib_exists = os.path.exists(allowed_docs.get("ib-data")) if allowed_docs.get("ib-data") else False
        
        options_tracker_url = config.get("external_services", {}).get("options_tracker_url", "")
        if "/api/positions" in options_tracker_url:
            options_tracker_main_url = options_tracker_url.replace("/api/positions", "")
        else:
            options_tracker_main_url = options_tracker_url
            
        base_template = self.env.get_template('base.html')
        nav_items = [{"name": "All", "url": "portfolio_active.html", "id": "pill-active", "slug": "all"}]
        
        rendered = base_template.render(
            TITLE="Dividend Calendar",
            CSS=css_rendered,
            JS=js_rendered,
            CONTENT=content_rendered,
            NAV_ITEMS=nav_items,
            CAT_NAV=category_nav or [],
            PORT_NAV=port_nav or [],
            JSON_FILENAME=json_filename,
            IB_DATA_EXISTS=ib_exists,
            PAGE_WIDTH=page_width,
            OPTIONS_TRACKER_URL=options_tracker_main_url,
            BACKTESTER_URL=config.get("external_services", {}).get("backtester_url", ""),
            GENERATED_AT_SGT=self.data["metadata"].get('generated_at_sgt')
        )
        
        return rendered, cal_data
