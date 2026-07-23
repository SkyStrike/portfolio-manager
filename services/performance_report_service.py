from datetime import datetime

def slugify(text):
    """Generates URL-safe IDs for HTML anchors and TOC linking."""
    if not text: return ""
    text = str(text).lower()
    text = re.sub(r'[^\w\s\-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

def build_chart_data(years, cash_data, portfolio_data, broker_cash_data=None, daily_cash_series=None, daily_broker_cash_series=None):
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

    def build_sub_series(series_entries):
        if not series_entries:
            return {"daily_cumulative": {"dates": [], "values": []}, "weekly_cumulative": {"dates": [], "values": []}}
        
        # 1. Daily
        daily_dates = []
        daily_vals = []
        for r in series_entries:
            try:
                dt_obj = datetime.strptime(r["date"], "%Y-%m-%d")
                daily_dates.append(dt_obj.strftime("%d %b"))
            except:
                daily_dates.append(r["date"])
            daily_vals.append(r2(r["gains"]))

        # 2. Weekly (group by isocalendar week and pick the last available record per week)
        weeks = {}
        for r in series_entries:
            try:
                dt_obj = datetime.strptime(r["date"], "%Y-%m-%d")
                iso_yr, iso_wk, _ = dt_obj.isocalendar()
                weeks[(iso_yr, iso_wk)] = r
            except:
                pass
        
        weekly_records = sorted(weeks.values(), key=lambda x: x["date"])
        weekly_dates = []
        weekly_vals = []
        for r in weekly_records:
            try:
                dt_obj = datetime.strptime(r["date"], "%Y-%m-%d")
                weekly_dates.append(dt_obj.strftime("%d %b"))
            except:
                weekly_dates.append(r["date"])
            weekly_vals.append(r2(r["gains"]))

        return {
            "daily_cumulative": {"dates": daily_dates, "values": daily_vals},
            "weekly_cumulative": {"dates": weekly_dates, "values": weekly_vals}
        }
            
    # 1. Cash chart data
    for y in years:
        y_data = cash_data.get(y, {})
        d_series = (daily_cash_series or {}).get(y, [])
        sub_chart = build_sub_series(d_series)

        raw_chart["cash"][y] = {
            "cumulative": [r2(y_data.get(m, {}).get("base_capital_gains")) for m in range(1, 13)],
            "daily_cumulative": sub_chart["daily_cumulative"],
            "weekly_cumulative": sub_chart["weekly_cumulative"],
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
                "mtm_val": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_val")) for m in range(1, 13)],
                "mtm_pct": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_pct")) for m in range(1, 13)]
            }
            
    # 3. Broker cash chart data
    if broker_cash_data:
        for br, br_data in broker_cash_data.items():
            raw_chart["broker_cash"][br] = {}
            for y in years:
                y_data = br_data.get(y, {})
                d_series = (daily_broker_cash_series or {}).get(br, {}).get(y, [])
                sub_chart = build_sub_series(d_series)

                raw_chart["broker_cash"][br][y] = {
                    "cumulative": [r2(y_data.get(m, {}).get("base_capital_gains")) for m in range(1, 13)],
                    "daily_cumulative": sub_chart["daily_cumulative"],
                    "weekly_cumulative": sub_chart["weekly_cumulative"],
                    "mtd_val": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_val")) for m in range(1, 13)],
                    "mtd_pct": [r2(y_data.get(m, {}).get("mtd", {}).get("base_capital_gains_pct")) for m in range(1, 13)],
                    "mtm_val": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_val")) for m in range(1, 13)],
                    "mtm_pct": [r2(y_data.get(m, {}).get("mtm", {}).get("base_capital_gains_pct")) for m in range(1, 13)]
                }
            
    return raw_chart


