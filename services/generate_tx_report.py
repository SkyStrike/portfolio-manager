import json
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from collections import defaultdict

def commas(value, precision=2, sign=False):
    if value is None: return "0.00"
    fmt = f"{{:,.{precision}f}}"
    if sign and value > 0: fmt = "+" + fmt
    return fmt.format(value)

def format_qty(value):
    if value is None: return "0"
    if value == int(value): return str(int(value))
    return f"{value:g}"

def round_sign(value, precision=2):
    if value is None: return "0"
    fmt = f"{{:+.{precision}f}}"
    return fmt.format(value)

def month_name(month_num):
    names = {
        "01": "January", "02": "February", "03": "March", "04": "April",
        "05": "May", "06": "June", "07": "July", "08": "August",
        "09": "September", "10": "October", "11": "November", "12": "December"
    }
    return names.get(month_num, month_num)

def slugify(text):
    if not text: return ""
    import re
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '-', text)

class TransactionReportGenerator:
    def __init__(self, data_or_path, template_dir='templates'):
        if isinstance(data_or_path, dict):
            self.data = data_or_path
        else:
            with open(data_or_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        import os
        base_path = os.getenv("BASE_PATH", "").strip()
        if base_path and not base_path.startswith("/"):
            base_path = "/" + base_path
        self.env.globals['BASE_PATH'] = base_path
        
        self.env.filters['commas'] = commas
        self.env.filters['slugify'] = slugify
        self.env.filters['format_qty'] = format_qty
        self.env.filters['round_sign'] = round_sign
        self.env.filters['month_name'] = month_name
        
    def generate(self, output_path=None, json_filename="portfolio_data.json", category_nav=None, port_nav=None):
        # Build the tree and the Search Index
        tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        underlying_totals = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        month_totals = defaultdict(lambda: defaultdict(float))
        year_totals = defaultdict(float)
        global_summary = {"expense": 0.0, "income": 0.0, "net": 0.0}
        search_index = []
        
        tx_counter = 0
        for pos in self.data['positions']:
            symbol = pos['symbol']
            underlying = pos['underlying']
            is_closed = pos['is_closed']
            current_price = pos['metrics'].get('current_price', 0)
            rate = pos.get('rate', 1.0)
            
            for tx in pos['transactions']:
                date = tx['date']
                year = date[:4]
                month = date[5:7]
                
                enriched_tx = tx.copy()
                enriched_tx['id'] = f"tx-{tx_counter}"
                enriched_tx['symbol'] = symbol
                enriched_tx['is_closed'] = is_closed
                
                val_raw = tx['qty'] * tx['price']
                if tx['action'] == 'Buy':
                    enriched_tx['total_net'] = val_raw + tx['fee']
                    tx_sgd_impact = enriched_tx['total_net'] * rate
                    global_summary["expense"] += tx_sgd_impact
                else:
                    enriched_tx['total_net'] = val_raw - tx['fee']
                    tx_sgd_impact = -enriched_tx['total_net'] * rate
                    global_summary["income"] += abs(tx_sgd_impact)
                
                enriched_tx['sgd_impact'] = tx_sgd_impact
                
                underlying_totals[year][month][underlying] += tx_sgd_impact
                month_totals[year][month] += tx_sgd_impact
                year_totals[year] += tx_sgd_impact
                global_summary["net"] += tx_sgd_impact

                if tx['action'] == 'Buy' and not is_closed:
                    buy_qty = tx['qty']
                    enriched_tx['current_val'] = buy_qty * current_price
                    enriched_tx['gain_pct'] = (((enriched_tx['current_val'] - val_raw) / val_raw) * 100) if val_raw > 0 else 0
                
                tree[year][month][underlying].append(enriched_tx)
                
                # Add to Search Index
                search_index.append({
                    "id": enriched_tx['id'],
                    "search": f"{symbol} {underlying}".upper(),
                    "flow": tx_sgd_impact,
                    "year": year,
                    "month": f"{year}-{month}",
                    "und": f"{year}-{month}-{slugify(underlying)}"
                })
                tx_counter += 1
        
        # Sort transactions within each underlying by date
        for y in tree:
            for m in tree[y]:
                for u in tree[y][m]:
                    tree[y][m][u].sort(key=lambda x: x['date'], reverse=True)

        latest_year = None
        latest_month = None
        if tree:
            latest_year = max(tree.keys())
            if tree[latest_year]:
                latest_month = max(tree[latest_year].keys())

        template = self.env.get_template('transaction_report.html')
        content_rendered = template.render(
            tree=tree,
            underlying_totals=underlying_totals,
            month_totals=month_totals,
            year_totals=year_totals,
            global_summary=global_summary,
            latest_year=latest_year,
            latest_month=latest_month,
            search_index=search_index
        )

        base_template = self.env.get_template('base.html')
        # Get UI settings from metadata
        from services.css_helper import render_combined_css
        ui_config = self.data.get('metadata', {}).get('config', {}).get('ui', {})
        font_size = ui_config.get('font_size', '14px')
        mobile_font_size = ui_config.get('mobile_font_size', '12px')
        page_width = ui_config.get('page_width', '1300px')
        
        css_rendered = render_combined_css(self.env, page_width=page_width, chart_height="40vh")

        js_template = self.env.get_template('scripts.js')
        js_rendered = js_template.render(
            COLOR_INVESTED='#2ecc71', 
            COLOR_CURRENT='#3498db',
            COLOR_RETURNS='#2ecc71',
            COLOR_INCOME='#2ecc71',
            COLOR_POSITIVE='#3498db',
            COLOR_NEGATIVE='#e74c3c',
            UI_FONT_SIZE=font_size,
            UI_MOBILE_FONT_SIZE=mobile_font_size
        )

        # Replicate nav scanning from report_renderer.py
        nav_items = [{"name": "All", "url": "portfolio_active.html", "id": "pill-active"}]
        if category_nav is None:
            category_nav = []
            if output_path is not None:
                src_dir = os.path.join(os.path.dirname(output_path), "src")
                if os.path.exists(src_dir):
                    json_files = [f for f in os.listdir(src_dir) if f.startswith("portfolio_data_") and f.endswith(".json") and f != "portfolio_data.json"]
                    for f in sorted(json_files):
                        slug = f.replace("portfolio_data_", "").replace(".json", "")
                        try:
                            with open(os.path.join(src_dir, f), 'r', encoding='utf-8') as jf:
                                cat_data = json.load(jf)
                                display_name = cat_data['metadata'].get('classification', slug.replace("-", " ").title())
                            category_nav.append({
                                "name": display_name,
                                "url": f"portfolio_active_{slug}.html",
                                "id": f"pill-active-{slug}",
                                "slug": slug
                            })
                        except Exception:
                            pass

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

        html_out = base_template.render(
            TITLE="Transaction History",
            CSS=css_rendered,
            JS=js_rendered,
            CONTENT=content_rendered,
            NAV_ITEMS=nav_items,
            CAT_NAV=category_nav,
            PORT_NAV=port_nav or [],
            IB_DATA_EXISTS=ib_exists,
            JSON_FILENAME=json_filename,
            GENERATED_AT_SGT=self.data.get('metadata', {}).get('generated_at_sgt', datetime.now().strftime("%Y-%m-%d %H:%M:%S SGT")),
            PAGE_WIDTH=page_width,
            OPTIONS_TRACKER_URL=options_tracker_main_url,
            BACKTESTER_URL=config.get("external_services", {}).get("backtester_url", "")
        )
        
        if output_path is not None:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_out)
        return html_out

if __name__ == "__main__":
    input_json = os.path.join("output", "src", "portfolio_data.json")
    output_html = os.path.join("output", "transaction_history.html")
    
    if not os.path.exists(input_json):
        print(f"Error: {input_json} not found. Run process_transactions.py first.")
    else:
        gen = TransactionReportGenerator(input_json)
        gen.generate(output_html)
        print(f"Transaction report generated: {output_html}")
