import json
import os
import re
from datetime import datetime
from core.performance_calculator import get_performance_report_data

def slugify(text):
    """Generates URL-safe IDs for HTML anchors and TOC linking."""
    if not text: return ""
    text = str(text).lower()
    text = re.sub(r'[^\w\s\-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

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
