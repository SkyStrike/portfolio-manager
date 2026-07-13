import json
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader

# --- Helpers ---

def slugify(text):
    """Generates URL-safe IDs for HTML anchors and TOC linking."""
    if not text: return ""
    text = str(text).lower()
    text = re.sub(r'[^\w\s\-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

def format_qty(qty):
    """Formats quantity to 4 decimal places for high-precision assets."""
    return f"{qty:,.4f}".rstrip('0').rstrip('.')

def roi_filter(val):
    """Formats ROI with a sign and 2 decimal places."""
    try:
        val = float(val)
        return f"{val:+.2f}%"
    except:
        return val

def groupby_year(records):
    """Groups a list of dicts by the year in their 'date' field."""
    grouped = defaultdict(list)
    for r in records:
        year = r['date'][:4]
        grouped[year].append(r)
    return dict(grouped)

# --- Renderer Class ---

class ReportRenderer:
    def __init__(self, json_data):
        self.data = json_data
        self.meta = json_data['metadata']
        self.config = self.meta.get('config', {})
        self.dash = json_data['dashboard']
        self.positions = json_data['positions']
        
        self.ui = self.config.get('ui', {})
        self.colors = self.ui.get('colors', {})
        self.template_dir = 'templates'
        
        self.cash_report = json_data.get('cash_report')

        # Setup Jinja2 (Autoescape disabled to preserve existing HTML string building where used)
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )
        base_path = os.getenv("BASE_PATH", "").strip()
        if base_path and not base_path.startswith("/"):
            base_path = "/" + base_path
        self.env.globals['BASE_PATH'] = base_path
        
        # Register Filters
        self.env.filters['slugify'] = slugify
        self.env.filters['format_qty'] = format_qty
        self.env.filters['commas'] = lambda val, p=2, sign=False: f"{'+' if sign and float(val)>0 else ''}{float(val):,.{p}f}"
        self.env.filters['roi'] = roi_filter
        self.env.filters['groupby_year'] = groupby_year
        self.env.filters['round'] = lambda val, p=2, sign=False: f"{'+' if sign and float(val)>0 else ''}{round(float(val), p)}"
        self.env.filters['map_qty'] = lambda txs: sum(t['qty'] if t['action'] == 'Buy' else -t['qty'] for t in txs)
        self.env.filters['map_val'] = lambda txs: sum(t['qty']*t['price'] if t['action'] == 'Buy' else -t['qty']*t['price'] for t in txs)
        self.env.filters['tojson'] = lambda obj: json.dumps(obj)

    def _get_css(self, is_closed=False):
        from services.css_helper import render_combined_css
        page_width = self.ui.get('page_width', '1300px')
        
        return render_combined_css(
            self.env,
            page_width=page_width,
            chart_height=self.ui.get('chart_height', '40vh')
        )

    def _get_js(self):
        template = self.env.get_template('scripts.js')
        c = self.colors
        defaults = {
            'invested': '#7f8c8d', 'current': '#3498db', 'returns': '#2ecc71',
            'income': '#2ecc71', 'positive': '#3498db', 'negative': '#e74c3c'
        }
        return template.render(
            COLOR_INVESTED=c.get('invested', defaults['invested']),
            COLOR_CURRENT=c.get('current', defaults['current']),
            COLOR_RETURNS=c.get('returns', defaults['returns']),
            COLOR_INCOME=c.get('income', defaults['income']),
            COLOR_POSITIVE=c.get('positive', defaults['positive']),
            COLOR_NEGATIVE=c.get('negative', defaults['negative']),
            UI_FONT_SIZE=self.ui.get('font_size', '14px'),
            UI_MOBILE_FONT_SIZE=self.ui.get('mobile_font_size', '12px')
        )

    def render_active(self, nav_items=None, cat_nav=None, port_nav=None, json_filename="portfolio_data.json"):
        return self._render_page(is_closed=False, nav_items=nav_items, cat_nav=cat_nav, port_nav=port_nav, json_filename=json_filename)

    def render_closed(self, nav_items=None, cat_nav=None, port_nav=None, json_filename="portfolio_data.json"):
        return self._render_page(is_closed=True, nav_items=nav_items, cat_nav=cat_nav, port_nav=port_nav, json_filename=json_filename)

    def _prepare_country_breakdown(self):
        country_vals = defaultdict(float)
        for p in self.positions:
            if p.get('is_closed', False):
                continue
            val = p.get('sgd_metrics', {}).get('current_sgd', 0.0)
            if val <= 0:
                continue

            ex = (p.get('exchange') or "").strip().upper()
            if ex in ["SG", "SI"]:
                country = "Singapore"
            elif ex in ["TO", "TSE", "V", "TSX", "NEO", "NE", "CSE"]:
                country = "Canada"
            else:
                country = "US"

            country_vals[country] += val

        total_val = sum(country_vals.values())
        country_list = []
        for c_name, val in country_vals.items():
            pct = (val / total_val * 100) if total_val > 0 else 0.0
            country_list.append({
                "name": c_name,
                "value": val,
                "pct": pct
            })
        return sorted(country_list, key=lambda x: x['value'], reverse=True)

    def render_charts(self, nav_items=None, cat_nav=None, port_nav=None, json_filename="portfolio_data.json"):
        self.dash['countries'] = self._prepare_country_breakdown()
        template = self.env.get_template('charts_page.html')
        return self._wrap_body(
            template.render(
                dashboard=self.dash,
                meta=self.meta,
                total_market=self.meta['summary']['total_market_value_sgd'],
                NAV_ITEMS=nav_items or [],
                CAT_NAV=cat_nav or [],
                JSON_FILENAME=json_filename
            ),
            title="Portfolio Charts",
            is_closed=False,
            nav_items=nav_items,
            cat_nav=cat_nav,
            port_nav=port_nav,
            json_filename=json_filename
        )

    def _sort_classifications(self, hierarchy):
        """Sorts classifications based on priority and market value."""
        priority = self.config.get('sorting', {}).get('classification_priority', [])
        
        def sort_key(c_name):
            p_index = priority.index(c_name) if c_name in priority else 999
            # Secondary sort by total market value descending
            total_val = sum(p['sgd_metrics']['current_sgd'] for u in hierarchy[c_name].values() for p in u)
            return (p_index, -total_val)
            
        return sorted(hierarchy.keys(), key=sort_key)

    def _get_last_sell_date_parts(self, position):
        """Extracts Year and Full Month Name from the last sell transaction."""
        sell_dates = [t['date'] for t in position['transactions'] if t['action'] == 'Sell']
        if sell_dates:
            last_sell = max(sell_dates)
        else:
            all_dates = [t['date'] for t in position['transactions']] + [i['date'] for i in position.get('income', [])]
            last_sell = max(all_dates) if all_dates else datetime.now().strftime('%Y-%m-%d')
            
        month_part = last_sell[5:7] if len(last_sell) >= 7 else "01"
        try:
            dt = datetime.strptime(month_part, "%m")
        except ValueError:
            dt = datetime.strptime("01", "%m")
            
        return last_sell[:4] if len(last_sell) >= 4 else "0000", dt.strftime("%B"), dt.month

    def _get_aggregated_metrics(self, symbols, is_closed):
        """Calculates combined metrics for a list of symbols."""
        metrics = {
            "curr": sum(p['sgd_metrics']['current_sgd'] for p in symbols),
            "inv": sum(p['sgd_metrics']['invested_sgd'] for p in symbols),
            "gl": sum(p['sgd_metrics']['profit_sgd'] for p in symbols),
            "inc": sum(p['sgd_metrics']['income_sgd'] for p in symbols),
            "fee": sum(p['sgd_metrics']['fees_sgd'] for p in symbols),
            "cap_gain": sum(p['metrics']['capital_gain_sgd'] for p in symbols),
            "realized_pnl": sum(p['sgd_metrics']['realized_pnl_sgd'] for p in symbols),
            "ret": sum(p['sgd_metrics']['total_returns_sgd'] for p in symbols),
            "daily_val": sum(p['sgd_metrics']['daily_val_sgd'] for p in symbols),
            "days": max((p['metrics']['days_since_first_tx'] for p in symbols), default=0)
        }
        metrics["roi"] = (metrics["gl"] / metrics["inv"] * 100) if metrics["inv"] > 0 else 0
        
        prev_curr = metrics["curr"] - metrics["daily_val"]
        metrics["daily_pct"] = (metrics["daily_val"] / prev_curr * 100) if prev_curr > 0 else 0
        return metrics

    def _prepare_active_report(self):
        """Prepares data for the Active Portfolio report."""
        hierarchy = defaultdict(lambda: defaultdict(list))
        for p in self.positions:
            if not p['is_closed']:
                hierarchy[p['classification']][p['underlying']].append(p)
        
        total_market = self.meta['summary']['total_market_value_sgd']
        sorted_classes = self._sort_classifications(hierarchy)

        sections = {}
        body_groups = []
        for cl in sorted_classes:
            und_data = self._process_underlyings(hierarchy[cl], is_closed=False)
            cl_val = sum(u['curr'] for u in und_data.values())
            cl_inv = sum(u['inv'] for u in und_data.values())
            cl_inc = sum(u['inc'] for u in und_data.values())
            cl_cap_gain = sum(u['cap_gain'] for u in und_data.values())
            cl_realized_pnl = sum(u['realized_pnl'] for u in und_data.values())
            cl_daily_val = sum(u['daily_val'] for u in und_data.values())
            cl_gl = sum(u['gl'] for u in und_data.values())
            
            section_data = {
                "title": cl,
                "total_pct": (cl_val / total_market * 100) if total_market > 0 else 0,
                "curr": cl_val,
                "inv": cl_inv,
                "inc": cl_inc,
                "cap_gain": cl_cap_gain,
                "realized_pnl": cl_realized_pnl,
                "daily_val": cl_daily_val,
                "gl": cl_gl,
                "underlyings": und_data
            }
            sections[cl] = section_data
            body_groups.append(section_data)
            
        return {"toc": sections, "body": body_groups}

    def _prepare_closed_report(self):
        """Prepares data for the Closed Positions report with Year > Month hierarchy.
        Each month group carries a flat list of positions (no underlying grouping).
        """
        hierarchy = defaultdict(lambda: defaultdict(list))
        for p in self.positions:
            if p['is_closed']:
                year, month_name, _ = self._get_last_sell_date_parts(p)
                hierarchy[year][month_name].append(p)

        sorted_years = sorted(hierarchy.keys(), reverse=True)
        toc_sections = {}
        body_groups = []

        for yr in sorted_years:
            yr_profit = 0
            months_data = {}
            # Sort months by calendar order (most recent first)
            sorted_months = sorted(
                hierarchy[yr].keys(),
                key=lambda m: datetime.strptime(m, "%B").month,
                reverse=True
            )

            for mo in sorted_months:
                positions = sorted(
                    hierarchy[yr][mo],
                    key=lambda p: p['sgd_metrics']['profit_sgd'],
                    reverse=True
                )
                mo_profit = sum(p['sgd_metrics']['profit_sgd'] for p in positions)
                yr_profit += mo_profit

                month_section = {
                    "title": f"{yr} - {mo}",
                    "month_name": mo,
                    "year": yr,
                    "total_gl": mo_profit,
                    "positions": positions,
                }
                months_data[mo] = month_section
                body_groups.append(month_section)

            toc_sections[yr] = {
                "total_gl": yr_profit,
                "months": months_data
            }

        return {"toc": toc_sections, "body": body_groups}

    def _process_underlyings(self, unds_dict, is_closed):
        """Helper to process a dict of underlying: [positions] into the template format."""
        total_market = self.meta['summary']['total_market_value_sgd']
        total_invested = self.meta['summary']['total_invested_active_sgd']
        und_data = {}
        
        # Sort underlyings by profit/current value
        sorted_unds = sorted(
            unds_dict.items(), 
            key=lambda x: sum(p['sgd_metrics']['current_sgd' if not is_closed else 'profit_sgd'] for p in x[1]), 
            reverse=True
        )
        
        for u_name, symbols in sorted_unds:
            metrics = self._get_aggregated_metrics(symbols, is_closed)
            
            backtester_base = self.config.get("external_services", {}).get("backtester_url")
            backtest_url = None
            if backtester_base and not is_closed:
                from services.price_service import get_yfinance_symbol
                yf_tickers = {get_yfinance_symbol(p['symbol'], p.get('exchange')) for p in symbols}
                tickers_list = sorted(list(yf_tickers))
                tickers_param = ",".join(tickers_list)
                all_dates = []
                for p in symbols:
                    for tx in p.get('transactions', []):
                        if tx.get('date'):
                            all_dates.append(tx['date'])
                earliest_date = min(all_dates) if all_dates else "2025-01-01"
                from datetime import date
                today_str = date.today().strftime("%Y-%m-%d")
                if not backtester_base.endswith("/"):
                    backtester_base += "/"
                backtest_url = f"{backtester_base}?tickers={tickers_param}&startDate={earliest_date}&endDate={today_str}"

            und_data[u_name] = {
                **metrics,
                "backtest_url": backtest_url,
                "alloc_pct": (metrics["curr"] / total_market * 100) if total_market > 0 and not is_closed else 0,
                "invested_pct": (metrics["inv"] / total_invested * 100) if total_invested > 0 and not is_closed else 0,
                "symbols": sorted(
                    symbols, 
                    key=lambda x: x['sgd_metrics']['current_sgd'] if not is_closed else x['sgd_metrics']['profit_sgd'], 
                    reverse=True
                )
            }
        return und_data



    def _prepare_recent_transactions(self):
        """Prepares transactions for the past month grouped by week."""
        all_txs = []
        for p in self.positions:
            rate = p.get('rate', 1.0)
            symbol = p['symbol']
            underlying = p['underlying']
            is_closed = p['is_closed']
            current_price = p['metrics'].get('current_price', 0)
            
            for tx in p['transactions']:
                enriched = tx.copy()
                enriched['symbol'] = symbol
                enriched['underlying'] = underlying
                enriched['is_closed'] = is_closed
                enriched['current_price'] = current_price
                
                val_raw = tx['qty'] * tx['price']
                if tx['action'] == 'Buy':
                    enriched['total_net'] = val_raw + tx['fee']
                    enriched['sgd_impact'] = enriched['total_net'] * rate
                else:
                    enriched['total_net'] = val_raw - tx['fee']
                    enriched['sgd_impact'] = -enriched['total_net'] * enriched['rate'] if 'rate' in enriched else -enriched['total_net'] * rate
                
                if tx['action'] == 'Buy' and not is_closed:
                    buy_qty = tx['qty']
                    enriched['current_val'] = buy_qty * current_price
                    enriched['gain_pct'] = (((enriched['current_val'] - val_raw) / val_raw) * 100) if val_raw > 0 else 0
                
                all_txs.append(enriched)

        # Filter for the last 4 weeks (28 days)
        gen_at_str = self.meta.get('generated_at')
        if not gen_at_str:
            gen_at = datetime.now()
        else:
            try:
                gen_at = datetime.fromisoformat(gen_at_str)
            except:
                gen_at = datetime.now()
                
        start_date = gen_at - timedelta(weeks=4)
        
        recent_txs = []
        for tx in all_txs:
            try:
                tx_date = datetime.strptime(tx['date'], '%Y-%m-%d')
                if tx_date >= start_date:
                    recent_txs.append(tx)
            except:
                continue

        # Group by week (starting Monday)
        weeks = defaultdict(list)
        for tx in recent_txs:
            dt = datetime.strptime(tx['date'], '%Y-%m-%d')
            # weekday() returns 0 for Monday, 6 for Sunday
            monday = dt - timedelta(days=dt.weekday())
            week_key = monday.strftime('%Y-%m-%d')
            weeks[week_key].append(tx)
        
        # Format for template
        sorted_weeks = []
        total_month_flow = 0
        for week_start in sorted(weeks.keys(), reverse=True):
            week_txs = weeks[week_start]
            week_flow = sum(tx['sgd_impact'] for tx in week_txs)
            buy_flow = sum(tx['sgd_impact'] for tx in week_txs if tx['action'].lower() == 'buy')
            sell_flow = sum(tx['sgd_impact'] for tx in week_txs if tx['action'].lower() != 'buy')
            total_month_flow += week_flow
            
            # Find week range string
            monday_dt = datetime.strptime(week_start, '%Y-%m-%d')
            sunday_dt = monday_dt + timedelta(days=6)
            week_range = f"{monday_dt.strftime('%d %b')} - {sunday_dt.strftime('%d %b')}"
            
            sorted_weeks.append({
                "start": week_start,
                "range": week_range,
                "flow": week_flow,
                "buy_flow": buy_flow,
                "sell_flow": sell_flow,
                "transactions": sorted(week_txs, key=lambda x: x['date'], reverse=True)
            })
            
        return {
            "month_flow": total_month_flow,
            "weeks": sorted_weeks,
            "month_name": "Last 4 Weeks"
        }

    def _render_page(self, is_closed, nav_items=None, cat_nav=None, port_nav=None, json_filename="portfolio_data.json"):
        report_data = self._prepare_active_report() if not is_closed else self._prepare_closed_report()

        if is_closed:
            template = self.env.get_template('portfolio_closed_report.html')
            return self._wrap_body(
                template.render(
                    sections=report_data['toc'],
                    render_groups=report_data['body'],
                    meta=self.meta,
                    positions=self.positions,
                    sum_exit_value=lambda p: sum(t['qty'] * t['price'] for t in p['transactions'] if t['action'] == 'Sell'),
                    NAV_ITEMS=nav_items or [],
                    CAT_NAV=cat_nav or [],
                    PORTFOLIO_NAMES=[p['name'] for p in (port_nav or [])],
                    JSON_FILENAME=json_filename
                ),
                title="Closed Positions",
                is_closed=True,
                nav_items=nav_items,
                cat_nav=cat_nav,
                port_nav=port_nav,
                json_filename=json_filename
            )

        # Active path
        template = self.env.get_template('portfolio_report.html')
        recent_tx_data = self._prepare_recent_transactions()
        return self._wrap_body(
            template.render(
                is_closed=False,
                dashboard=self.dash,
                sections=report_data['toc'],
                render_groups=report_data['body'],
                total_market=self.meta['summary']['total_market_value_sgd'],
                total_invested_capital=self.meta['summary']['total_invested_active_sgd'],
                meta=self.meta,
                positions=self.positions,
                cash_report=self.cash_report,
                recent_tx=recent_tx_data,
                open_options=self.data.get('open_options'),
                recent_closed_options=self.data.get('recent_closed_options'),
                sum_exit_value=lambda p: sum(t['qty'] * t['price'] for t in p['transactions'] if t['action'] == 'Sell'),
                NAV_ITEMS=nav_items or [],
                CAT_NAV=cat_nav or [],
                PORTFOLIO_NAMES=[p['name'] for p in (port_nav or [])],
                JSON_FILENAME=json_filename
            ),
            title="Active Portfolio",
            is_closed=False,
            nav_items=nav_items,
            cat_nav=cat_nav,
            port_nav=port_nav,
            json_filename=json_filename
        )

    # --- Content Sections ---

    def _wrap_body(self, content, title, is_closed=False, nav_items=None, cat_nav=None, port_nav=None, json_filename="portfolio_data.json"):
        template = self.env.get_template('base.html')
        from services.rebuild_dashboard import load_config
        config = load_config()
        allowed_docs = config.get("allowed_documents", {})
        ib_data_path = allowed_docs.get("ib-data")
        ib_exists = os.path.exists(ib_data_path) if ib_data_path else False

        # Resolve options tracker main URL
        options_tracker_url = config.get("external_services", {}).get("options_tracker_url", "")
        if "/api/positions" in options_tracker_url:
            options_tracker_main_url = options_tracker_url.replace("/api/positions", "")
        else:
            options_tracker_main_url = options_tracker_url

        return template.render(
            TITLE=title,
            CSS=self._get_css(is_closed),
            JS=self._get_js(),
            CONTENT=content,
            NAV_ITEMS=nav_items or [],
            CAT_NAV=cat_nav or [],
            PORT_NAV=port_nav or [],
            JSON_FILENAME=json_filename,
            IB_DATA_EXISTS=ib_exists,
            PAGE_WIDTH=self.ui.get('page_width', '1800px'),
            OPTIONS_TRACKER_URL=options_tracker_main_url,
            BACKTESTER_URL=config.get("external_services", {}).get("backtester_url", ""),
            GENERATED_AT_SGT=self.meta.get('generated_at_sgt') or datetime.now().strftime("%Y-%m-%d %H:%M:%S SGT")
        )

def main():
    output_dir = "output"
    src_dir = os.path.join(output_dir, "src")
    json_path = os.path.join(src_dir, "portfolio_data.json")
    if not os.path.exists(json_path):
        print("JSON data not found. Run process_transactions.py first.")
        return
        
    # 1. Discover all generated dashboards
    nav_items = [{"name": "All", "url": "portfolio_active.html", "id": "pill-active"}]
    category_nav = []
    
    # Scan for category-specific JSONs and their names
    json_files = [f for f in os.listdir(src_dir) if f.startswith("portfolio_data_") and f.endswith(".json") and f != "portfolio_data.json"]
    for f in sorted(json_files):
        slug = f.replace("portfolio_data_", "").replace(".json", "")
        with open(os.path.join(src_dir, f), 'r', encoding='utf-8') as jf:
            cat_data = json.load(jf)
            display_name = cat_data['metadata'].get('classification', slug.replace("-", " ").title())
        
        category_nav.append({
            "name": display_name,
            "url": f"portfolio_active_{slug}.html",
            "id": f"pill-active-{slug}",
            "slug": slug
        })

    # 2. Render Main Portfolio
    with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
    renderer = ReportRenderer(data)
    
    with open(os.path.join(output_dir, "portfolio_active.html"), "w", encoding="utf-8") as f: 
        f.write(renderer.render_active(nav_items=nav_items, cat_nav=category_nav, json_filename="portfolio_data.json"))
        
    with open(os.path.join(output_dir, "portfolio_closed.html"), "w", encoding="utf-8") as f: 
        f.write(renderer.render_closed(nav_items=nav_items, cat_nav=category_nav, json_filename="portfolio_data.json"))
        
    with open(os.path.join(output_dir, "charts.html"), "w", encoding="utf-8") as f: 
        f.write(renderer.render_charts(nav_items=nav_items, cat_nav=category_nav, json_filename="portfolio_data.json"))

    # 3. Render Individual Category Dashboards
    for f in json_files:
        slug = f.replace("portfolio_data_", "").replace(".json", "")
        with open(os.path.join(src_dir, f), 'r', encoding='utf-8') as jf:
            cat_data = json.load(jf)
        
        cat_renderer = ReportRenderer(cat_data)
        display_name = cat_data['metadata'].get('classification', slug.title())
        
        with open(os.path.join(output_dir, f"portfolio_active_{slug}.html"), "w", encoding="utf-8") as out_f:
            out_f.write(cat_renderer.render_active(nav_items=nav_items, cat_nav=category_nav, json_filename=f))
            
        with open(os.path.join(output_dir, f"portfolio_closed_{slug}.html"), "w", encoding="utf-8") as out_f:
            out_f.write(cat_renderer.render_closed(nav_items=nav_items, cat_nav=category_nav, json_filename=f))
            
        with open(os.path.join(output_dir, f"charts_{slug}.html"), "w", encoding="utf-8") as out_f:
            out_f.write(cat_renderer.render_charts(nav_items=nav_items, cat_nav=category_nav, json_filename=f))

    print("Reports Generated")

if __name__ == "__main__":
    main()
