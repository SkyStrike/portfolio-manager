import json
import os
import re
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from core.performance_calculator import get_performance_report_data

def slugify(text):
    """Generates URL-safe IDs for HTML anchors and TOC linking."""
    if not text: return ""
    text = str(text).lower()
    text = re.sub(r'[^\w\s\-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

class PerformanceReportRenderer:
    def __init__(self, config_data):
        self.config = config_data
        self.ui = self.config.get('ui', {})
        self.colors = self.ui.get('colors', {})
        self.template_dir = 'templates'
        
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
        
        self.env.filters['slugify'] = slugify
        self.env.filters['commas'] = lambda val, p=2, sign=False: f"{'+' if sign and float(val)>0 else ''}{float(val):,.{p}f}"
        self.env.filters['round'] = lambda val, p=2, sign=False: f"{'+' if sign and float(val)>0 else ''}{round(float(val), p)}"
        self.env.filters['tojson'] = lambda obj: json.dumps(obj)

    def _get_css(self):
        from services.css_helper import render_combined_css
        return render_combined_css(
            self.env,
            page_width=self.ui.get('page_width', '1300px'),
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

    def render(self, data, raw_chart_data, nav_items, category_nav, port_nav=None, json_filename="portfolio_data.json"):
        template = self.env.get_template('performance_report.html')
        
        month_names = {
            1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
            7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
        }
        
        c = self.colors
        defaults = {
            'invested': '#7f8c8d', 'current': '#3498db', 'returns': '#2ecc71',
            'income': '#2ecc71', 'positive': '#3498db', 'negative': '#e74c3c'
        }
        content = template.render(
            years=data['years'],
            classifications=data['classifications'],
            cash_data=data['cash_data'],
            portfolio_data=data['portfolio_data'],
            cash_ytd=data.get('cash_ytd', {}),
            portfolio_ytd=data.get('portfolio_ytd', {}),
            broker_cash_data=data.get('broker_cash_data', {}),
            broker_cash_ytd=data.get('broker_cash_ytd', {}),
            month_names=month_names,
            raw_chart_data=raw_chart_data,
            COLOR_RETURNS=c.get('returns', defaults['returns']),
            COLOR_NEGATIVE=c.get('negative', defaults['negative']),
            BROKERS=self.config.get('brokers', ['IBKR', 'MOOMOO'])
        )
        
        base_template = self.env.get_template('base.html')
        from services.rebuild_dashboard import load_config
        config = load_config()
        allowed_docs = config.get("allowed_documents", {})
        ib_data_path = allowed_docs.get("ib-data", "data/ib_data.json")
        ib_exists = os.path.exists(ib_data_path)
        
        # Resolve options tracker main URL
        options_tracker_url = config.get("external_services", {}).get("options_tracker_url", "")
        if "/api/positions" in options_tracker_url:
            options_tracker_main_url = options_tracker_url.replace("/api/positions", "")
        else:
            options_tracker_main_url = options_tracker_url
        backtester_url = config.get("external_services", {}).get("backtester_url", "")
        
        return base_template.render(
            TITLE="Performance Report",
            CSS=self._get_css(),
            JS=self._get_js(),
            CONTENT=content,
            NAV_ITEMS=nav_items,
            CAT_NAV=category_nav,
            PORT_NAV=port_nav or [],
            IB_DATA_EXISTS=ib_exists,
            JSON_FILENAME=json_filename,
            GENERATED_AT_SGT=datetime.now().strftime("%Y-%m-%d %H:%M:%S SGT"),
            PAGE_WIDTH=self.ui.get('page_width', '1800px'),
            OPTIONS_TRACKER_URL=options_tracker_main_url,
            BACKTESTER_URL=backtester_url
        )

def build_chart_data(years, cash_data, portfolio_data, broker_cash_data=None):
    raw_chart = {
        "cash": {},
        "portfolio": {},
        "broker_cash": {}
    }
    
    def r2(val):
        if val is None:
            return None
        try:
            return round(float(val), 2)
        except:
            return val
            
    # 1. Cash chart data
    for y in years:
        y_data = cash_data.get(y, {})
        raw_chart["cash"][y] = {
            "cumulative": [r2(y_data.get(m, {}).get("base_capital_gains")) for m in range(1, 13)],
            "mtd_val": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_val")) for m in range(1, 13)],
            "mtd_pct": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_pct")) for m in range(1, 13)],
            "mtm_val": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_val")) for m in range(1, 13)],
            "mtm_pct": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_pct")) for m in range(1, 13)]
        }
        
    # 2. Portfolio chart data
    for cls, cls_data in portfolio_data.items():
        raw_chart["portfolio"][cls] = {}
        for y in years:
            y_data = cls_data.get(y, {})
            raw_chart["portfolio"][cls][y] = {
                "cumulative": [r2(y_data.get(m, {}).get("total_returns")) for m in range(1, 13)],
                "mtd_val": [r2(y_data.get(m, {}).get("mtd", {}).get("total_returns_val")) for m in range(1, 13)],
                "mtd_pct": [r2(y_data.get(m, {}).get("mtd", {}).get("total_returns_pct")) for m in range(1, 13)],
                "mtm_val": [r2(y_data.get(m, {}).get("mtm", {}).get("total_returns_val")) for m in range(1, 13)],
                "mtm_pct": [r2(y_data.get(m, {}).get("mtm", {}).get("total_returns_pct")) for m in range(1, 13)]
            }
            
    # 3. Broker cash chart data
    if broker_cash_data:
        for br, br_data in broker_cash_data.items():
            raw_chart["broker_cash"][br] = {}
            for y in years:
                y_data = br_data.get(y, {})
                raw_chart["broker_cash"][br][y] = {
                    "cumulative": [r2(y_data.get(m, {}).get("base_capital_gains")) for m in range(1, 13)],
                    "mtd_val": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_val")) for m in range(1, 13)],
                    "mtd_pct": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_pct")) for m in range(1, 13)],
                    "mtm_val": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_val")) for m in range(1, 13)],
                    "mtm_pct": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_pct")) for m in range(1, 13)]
                }
            
    return raw_chart

def main():
    db_path = "data/metrics.db"
    config_path = "data/config.json"
    if not os.path.exists(config_path):
        config_path = "config/config.json"
    if not os.path.exists(config_path):
        config_path = "config.json"
    output_dir = "output"
    src_dir = "output/src"
    
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return
        
    # Load config
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    else:
        config_data = {}
        
    # Get performance report data
    report_data = get_performance_report_data(db_path)
    
    # Build chart data
    raw_chart_data = build_chart_data(
        report_data["years"], 
        report_data["cash_data"], 
        report_data["portfolio_data"],
        report_data.get("broker_cash_data")
    )
    
    # Replicate nav scanning from report_renderer.py
    nav_items = [{"name": "All", "url": "portfolio_active.html", "id": "pill-active"}]
    category_nav = []
    
    if os.path.exists(src_dir):
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

    # Render report
    renderer = PerformanceReportRenderer(config_data)
    html_content = renderer.render(report_data, raw_chart_data, nav_items, category_nav)
    
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "performance_report.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print("Performance Report Generated successfully: output/performance_report.html")

if __name__ == "__main__":
    main()
