from collections import defaultdict
from core.models import slugify

def build_dashboard(active_positions, all_positions, config, explicit_classifications=None):
    """
    Groups and aggregates all data required for the visual dashboard.
    This includes pie charts, income timelines, and strategy performance bar charts.
    """
    category_map = defaultdict(lambda: {"inv": 0, "curr": 0, "inc": 0, "profit": 0})
    class_map = defaultdict(lambda: {
        "inv": 0, "curr": 0, "inc": 0, "profit": 0, "daily_val": 0,
        "underlying": defaultdict(lambda: {"inv": 0, "curr": 0, "inc": 0, "profit": 0, "daily_val": 0, "symbols": []})
    })
    
    monthly_income = defaultdict(float)
    yearly_income = defaultdict(float)
    growth_assets, income_assets = [], []

    # 1. Process Income Timeline (All positions, any subclass)
    for p in all_positions:
        if not p.income_records:
            continue
            
        total_net = sum(r['net'] for r in p.income_records)
        if total_net != 0:
            rate = p.income_sgd / total_net
        else:
            rate = p.rate
            
        for record in p.income_records:
            val_sgd = record['net'] * rate
            monthly_income[record['date'][:7]] += val_sgd
            yearly_income[record['year']] += val_sgd

    # 2. Process Active Holdings & Strategy Visuals
    all_daily_stats = []
    for p in active_positions:
        s_name, c_name, u_name = p.category, p.classification, p.underlying
        inv, curr, inc, profit, daily_val = p.invested_sgd, p.current_sgd, p.income_sgd, p.profit_sgd, p.daily_val_sgd
        
        # Map over standard grouping levels
        for d in [category_map[s_name], class_map[c_name], class_map[c_name]["underlying"][u_name]]:
            d["inv"] += inv
            d["curr"] += curr
            d["inc"] += inc
            d["profit"] += profit
            if "daily_val" in d:
                d["daily_val"] += daily_val
        
        # Add symbol data for individual charts
        class_map[c_name]["underlying"][u_name]["symbols"].append(p.to_dict())
        
        all_daily_stats.append({
            "symbol": p.symbol,
            "val": daily_val,
            "pct": p.daily_pct
        })

        if s_name == 'growth': 
            growth_assets.append({
                "label": p.symbol, 
                "inv": inv, 
                "ret": curr + inc, 
                "roi": p.get_roi_percentage()
            })
        elif s_name == 'income': 
            income_assets.append({
                "label": p.symbol, 
                "inv": inv, 
                "curr": curr, 
                "ret": curr + inc, 
                "roi": p.get_roi_percentage()
            })

    # Calculate Top Gainers and Losers
    top_gainers_val = sorted([x for x in all_daily_stats if x["val"] > 0], key=lambda x: x["val"], reverse=True)[:10]
    top_losers_val = sorted([x for x in all_daily_stats if x["val"] < 0], key=lambda x: x["val"])[:10]
    top_gainers_pct = sorted([x for x in all_daily_stats if x["pct"] > 0], key=lambda x: x["pct"], reverse=True)[:10]
    top_losers_pct = sorted([x for x in all_daily_stats if x["pct"] < 0], key=lambda x: x["pct"])[:10]

    # Build final dashboard data object
    dashboard = {
        "portfolio_income": {
            "monthly": {
                "labels": sorted(monthly_income.keys()), 
                "values": [round(monthly_income[m], 2) for m in sorted(monthly_income.keys())]
            },
            "yearly": {
                "labels": sorted(yearly_income.keys()), 
                "values": [round(yearly_income[y], 2) for y in sorted(yearly_income.keys())]
            }
        },
        "categories": [],
        "subclasses": [],
        "growth_strategy": {
            "labels": [a['label'] for a in sorted(growth_assets, key=lambda x: x['ret'], reverse=True)], 
            "invested": [round(a['inv'], 2) for a in sorted(growth_assets, key=lambda x: x['ret'], reverse=True)], 
            "returns": [round(a['ret'], 2) for a in sorted(growth_assets, key=lambda x: x['ret'], reverse=True)], 
            "roi": [round(a['roi'], 2) for a in sorted(growth_assets, key=lambda x: x['ret'], reverse=True)]
        },
        "income_strategy": {
            "labels": [a['label'] for a in sorted(income_assets, key=lambda x: x['ret'], reverse=True)], 
            "invested": [round(a['inv'], 2) for a in sorted(income_assets, key=lambda x: x['ret'], reverse=True)], 
            "current": [round(a['curr'], 2) for a in sorted(income_assets, key=lambda x: x['ret'], reverse=True)], 
            "returns": [round(a['ret'], 2) for a in sorted(income_assets, key=lambda x: x['ret'], reverse=True)], 
            "roi": [round(a['roi'], 2) for a in sorted(income_assets, key=lambda x: x['ret'], reverse=True)]
        },
        "top_performers": {
            "gainers_val": {"labels": [x["symbol"] for x in top_gainers_val], "values": [round(x["val"], 2) for x in top_gainers_val]},
            "losers_val": {"labels": [x["symbol"] for x in top_losers_val], "values": [round(x["val"], 2) for x in top_losers_val]},
            "gainers_pct": {"labels": [x["symbol"] for x in top_gainers_pct], "values": [round(x["pct"], 2) for x in top_gainers_pct]},
            "losers_pct": {"labels": [x["symbol"] for x in top_losers_pct], "values": [round(x["pct"], 2) for x in top_losers_pct]}
        },
        "daily_performance": {},
        "classifications": []
    }

    # Format global category stats for pie charts
    for name in sorted(category_map.keys(), key=lambda x: category_map[x]["curr"], reverse=True):
        d = category_map[name]
        cat_item = {
            "name": name.capitalize(), 
            "inv": round(d["inv"], 2), 
            "curr": round(d["curr"], 2), 
            "ret": round(d["curr"] + d["inc"], 2), 
            "roi": round((d["profit"] / d["inv"] * 100) if d["inv"] > 0 else 0, 2)
        }
        dashboard["categories"].append(cat_item)
        dashboard["subclasses"].append(cat_item)

    # Sorting Classifications using priority list from config
    priority = config.get('sorting', {}).get('classification_priority', [])
    def sort_key(c_name):
        try: 
            return priority.index(c_name)
        except ValueError: 
            return 999

    sorted_class_names = sorted(
        class_map.keys(), 
        key=lambda x: (sort_key(x), -class_map[x]["curr"])
    )

    # Prepare Classification Summary and Underlying detail charts
    for c_name in sorted_class_names:
        d = class_map[c_name]
        u_sorted = sorted(
            d["underlying"].keys(), 
            key=lambda x: d["underlying"][x]["curr"], 
            reverse=True
        )
        
        u_data = {"labels": [], "inv": [], "curr_total": [], "roi": [], "daily_val": [], "daily_pct": []}
        for u_name in u_sorted:
            ud = d["underlying"][u_name]
            u_data["labels"].append(u_name)
            u_data["inv"].append(round(ud["inv"], 2))
            u_data["curr_total"].append(round(ud["inv"] + ud["profit"], 2))
            u_data["roi"].append(round((ud["profit"] / ud["inv"] * 100) if ud["inv"] > 0 else 0, 2))
            
            u_data["daily_val"].append(round(ud["daily_val"], 2))
            prev_curr = ud["curr"] - ud["daily_val"]
            u_data["daily_pct"].append(round((ud["daily_val"] / prev_curr * 100) if prev_curr > 0 else 0, 2))
        
        # Track Daily Performance charts for all classifications
        c_daily_val = d["daily_val"]
        c_prev_curr = d["curr"] - c_daily_val
        c_daily_pct = (c_daily_val / c_prev_curr * 100) if c_prev_curr > 0 else 0
        
        dashboard["daily_performance"][slugify(c_name)] = {
            "name": c_name,
            "labels": u_data["labels"],
            "val": u_data["daily_val"],
            "pct": u_data["daily_pct"],
            "summary": {
                "val": round(c_daily_val, 2),
                "pct": round(c_daily_pct, 2)
            }
        }


        # Standardized Series logic for summaries
        summary_series = [
            {"name": "Invested", "data": [round(d["inv"], 2)]}, 
            {"name": "Current", "data": [round(d["curr"], 2)]}, 
            {"name": "Total Returns", "data": [round(d["curr"] + d["inc"], 2)]}
        ]
        
        # Standardized Series logic for underlyings
        u_series = [
            {"name": "Invested", "data": u_data["inv"]}, 
            {"name": "Current", "data": u_data["curr_total"]}
        ]

        dashboard["classifications"].append({
            "name": c_name, 
            "slug": slugify(c_name), 
            "is_explicit": explicit_classifications is None or c_name in explicit_classifications,
            "show_summary": True, 
            "inv": round(d["inv"], 2), 
            "curr": round(d["curr"], 2), 
            "ret": round(d["curr"] + d["inc"], 2), 
            "roi": round((d["profit"] / d["inv"] * 100) if d["inv"] > 0 else 0, 2),
            "underlying_series": u_series, 
            "underlying": u_data, 
            "summary_series": summary_series,
            "underlying_raw": d["underlying"]
        })
        
    return dashboard
