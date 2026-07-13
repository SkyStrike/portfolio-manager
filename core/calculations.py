from datetime import datetime
import sqlite3
from services.fetch_exchange_rates import get_historical_exchange_rate

def calculate_holdings(portfolio_id: int, conn: sqlite3.Connection):
    """
    Chronologically processes all transactions for a portfolio and returns
    the current holdings (shares, cost basis) and updates transactions with running stats.
    """
    # Fetch all transactions for this portfolio sorted chronologically.
    # Same-day transactions are prioritized so that BUYs and SPLITs are calculated before SELLs to prevent transient negative share balances.
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.ticker_id, t.date, t.action, t.price, t.quantity, 
               t.currency, t.commission, t.cost_basis_after, t.realized_pl, t.realized_pl_sgd,
               tk.symbol, tk.friendly_name, tk.underlying
        FROM transactions t
        JOIN tickers tk ON t.ticker_id = tk.id
        WHERE t.portfolio_id = ?
        ORDER BY t.date ASC, 
                 CASE t.action 
                    WHEN 'BUY' THEN 1 
                    WHEN 'SPLIT' THEN 2 
                    WHEN 'SELL' THEN 3 
                    ELSE 4 
                 END ASC, 
                 t.id ASC
    """, (portfolio_id,))
    
    rows = cursor.fetchall()
    
    # Track holdings state per ticker: {ticker_id: {"shares": float, "avg_cost": float, "buy_chunks": list, "currency": str}}
    holdings = {}
    
    # We will update transactions in the DB with running cost basis and realized P&L
    updated_txs = []
    
    for row in rows:
        tx_id = row['id']
        ticker_id = row['ticker_id']
        action = row['action'].upper()
        price = float(row['price'])
        quantity = float(row['quantity'])
        currency = row['currency']
        symbol = row['symbol']
        name = row['friendly_name'] or symbol
        
        if ticker_id not in holdings:
            holdings[ticker_id] = {
                "ticker_id": ticker_id,
                "symbol": symbol,
                "name": name,
                "shares": 0.0,
                "avg_cost": 0.0,
                "buy_chunks": [], # list of [quantity, price, buy_rate]
                "currency": currency,
                "underlying": row["underlying"]
            }
            
        h = holdings[ticker_id]
        cost_basis_after = h["avg_cost"]
        realized_pl = 0.0
        realized_pl_sgd = 0.0
        
        if action == "BUY":
            rate = get_historical_exchange_rate(row['date'], currency, conn)
            h["buy_chunks"].append([quantity, price, rate])
            h["shares"] += quantity
            if h["shares"] > 0:
                total_cost = sum(c[0] * c[1] for c in h["buy_chunks"])
                h["avg_cost"] = total_cost / h["shares"]
            cost_basis_after = h["avg_cost"]
            realized_pl = 0.0
            realized_pl_sgd = 0.0
            
        elif action == "SELL":
            sell_qty = quantity
            rate = get_historical_exchange_rate(row['date'], currency, conn)
            proceeds_sgd = sell_qty * price * rate
            
            cost_native = 0.0
            cost_sgd = 0.0
            
            if h["shares"] > 0:
                sell_ratio = min(1.0, sell_qty / h["shares"])
                for c in h["buy_chunks"]:
                    chunk_sold_qty = c[0] * sell_ratio
                    cost_native += chunk_sold_qty * c[1]
                    cost_sgd += chunk_sold_qty * c[1] * c[2]
                    c[0] = c[0] * (1.0 - sell_ratio)
            
            realized_pl = (sell_qty * price) - cost_native
            realized_pl_sgd = proceeds_sgd - cost_sgd
            
            h["shares"] -= sell_qty
            if h["shares"] <= 0.00001:
                h["shares"] = 0.0
                h["avg_cost"] = 0.0
                h["buy_chunks"] = []
            else:
                total_cost = sum(c[0] * c[1] for c in h["buy_chunks"])
                h["avg_cost"] = total_cost / h["shares"]
            cost_basis_after = h["avg_cost"]
            
        elif action == "SPLIT":
            ratio = price
            if ratio > 0:
                h["shares"] = h["shares"] * ratio
                for c in h["buy_chunks"]:
                    c[0] *= ratio
                    c[1] /= ratio
                h["avg_cost"] = h["avg_cost"] / ratio
            cost_basis_after = h["avg_cost"]
            realized_pl = 0.0
            realized_pl_sgd = 0.0
            
        # Only write back to DB if calculated values differ from currently stored values
        curr_cb = row['cost_basis_after']
        curr_pl = row['realized_pl']
        curr_pl_sgd = row['realized_pl_sgd']
        if (curr_cb is None or abs((curr_cb or 0.0) - cost_basis_after) > 1e-5 or
            curr_pl is None or abs((curr_pl or 0.0) - realized_pl) > 1e-5 or
            curr_pl_sgd is None or abs((curr_pl_sgd or 0.0) - realized_pl_sgd) > 1e-5):
            updated_txs.append((cost_basis_after, realized_pl, realized_pl_sgd, tx_id))
        
    # Write running stats back to transactions table in a single transaction
    if updated_txs:
        conn.executemany("""
            UPDATE transactions 
            SET cost_basis_after = ?, realized_pl = ?, realized_pl_sgd = ?
            WHERE id = ?
        """, updated_txs)
        conn.commit()
        
    # Filter out holdings that are fully sold (shares == 0)
    active_holdings = {k: v for k, v in holdings.items() if v["shares"] > 0}
    return active_holdings

def get_portfolio_summary(portfolio_id: int | None, conn: sqlite3.Connection, exchange_rates: dict):
    """
    Computes holding-level details and a portfolio summary (or global net worth if portfolio_id is None).
    """
    cursor = conn.cursor()
    
    # 1. Fetch active tickers and their latest prices/prev_closes
    cursor.execute("""
        SELECT tp.ticker_id, tp.price, tp.prev_close, tp.currency, t.symbol, t.friendly_name, t.underlying
        FROM ticker_prices tp
        JOIN tickers t ON tp.ticker_id = t.id
    """)
    price_rows = cursor.fetchall()
    prices = {row['ticker_id']: {
        "price": row['price'],
        "prev_close": row['prev_close'] or row['price'],
        "currency": row['currency'],
        "underlying": row['underlying']
    } for row in price_rows}
    
    # 2. Get active portfolios
    if portfolio_id is not None:
        cursor.execute("SELECT id, name FROM portfolios WHERE id = ?", (portfolio_id,))
        portfolios = cursor.fetchall()
    else:
        cursor.execute("SELECT id, name FROM portfolios")
        portfolios = cursor.fetchall()
        
    portfolio_ids = [p['id'] for p in portfolios]
    
    # 3. Calculate holdings and compile summaries across selected portfolios
    all_holdings = {}
    total_realized_pl_sgd = 0.0
    
    for pid in portfolio_ids:
        # This will calculate holdings and update running database fields
        holdings = calculate_holdings(pid, conn)
        
        # Accumulate realized P&L from transactions table in SGD
        cursor.execute("""
            SELECT SUM(COALESCE(t.realized_pl_sgd, 0.0))
            FROM transactions t
            WHERE t.portfolio_id = ? AND t.action = 'SELL'
        """, (pid,))
        total_realized_pl_sgd += cursor.fetchone()[0] or 0.0
            
        # Combine holdings
        for ticker_id, h in holdings.items():
            if ticker_id not in all_holdings:
                all_holdings[ticker_id] = {
                    "ticker_id": h["ticker_id"],
                    "symbol": h["symbol"],
                    "name": h["name"],
                    "shares": 0.0,
                    "total_cost_native": 0.0,
                    "currency": h["currency"],
                    "underlying": h.get("underlying")
                }
            all_holdings[ticker_id]["shares"] += h["shares"]
            all_holdings[ticker_id]["total_cost_native"] += h["shares"] * h["avg_cost"]

    # 4. Fetch total dividends collected in SGD & calculate monthly cashflow
    dividend_query = "SELECT amount, currency, tax, date FROM dividends"
    params = ()
    if portfolio_id is not None:
        dividend_query += " WHERE portfolio_id = ?"
        params = (portfolio_id,)
    
    cursor.execute(dividend_query, params)
    div_rows = cursor.fetchall()
    total_dividends_gross_sgd = 0.0
    total_dividends_net_sgd = 0.0
    
    # Generate last 12 months keys chronologically (ending with current month)
    today = datetime.now()
    months_keys = []
    for i in range(11, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months_keys.append(f"{y:04d}-{m:02d}")
        
    monthly_dividends = {k: 0.0 for k in months_keys}
    
    for div in div_rows:
        amount = div['amount']
        tax = div['tax']
        currency = div['currency']
        date_str = div['date']
        rate = get_historical_exchange_rate(date_str, currency, conn)
        
        total_dividends_gross_sgd += amount * rate
        net_sgd = (amount - tax) * rate
        total_dividends_net_sgd += net_sgd
        
        if date_str:
            month = date_str[:7]
            if month in monthly_dividends:
                monthly_dividends[month] += net_sgd
        
    # 5. Populate detail metrics for each holding
    holdings_list = []
    total_value_sgd = 0.0
    total_cost_sgd = 0.0
    total_daily_pl_sgd = 0.0
    total_prev_close_value_sgd = 0.0
    
    for ticker_id, h in all_holdings.items():
        shares = h["shares"]
        currency = h["currency"]
        rate = exchange_rates.get(currency, 1.0)
        
        # Native average cost
        avg_cost_native = h["total_cost_native"] / shares
        total_cost_sgd += h["total_cost_native"] * rate
        
        # Latest price info
        price_info = prices.get(ticker_id, {"price": avg_cost_native, "prev_close": avg_cost_native, "currency": currency, "underlying": h.get("underlying")})
        current_price = price_info["price"]
        prev_close = price_info["prev_close"]
        
        # Value
        value_native = shares * current_price
        value_sgd = value_native * rate
        total_value_sgd += value_sgd
        
        # Total P&L (Unrealized)
        total_pl_native = value_native - h["total_cost_native"]
        total_pl_sgd = total_pl_native * rate
        total_pl_pct = (total_pl_native / h["total_cost_native"] * 100) if h["total_cost_native"] > 0 else 0.0
        
        # Daily P&L
        daily_diff_native = current_price - prev_close
        daily_pl_native = shares * daily_diff_native
        daily_pl_sgd = daily_pl_native * rate
        total_daily_pl_sgd += daily_pl_sgd
        
        daily_pl_pct = (daily_diff_native / prev_close * 100) if prev_close > 0 else 0.0
        
        # Accumulate previous close value in SGD for aggregate daily % change calculation
        prev_close_value_sgd = (shares * prev_close) * rate
        total_prev_close_value_sgd += prev_close_value_sgd
        
        holdings_list.append({
            "ticker_id": ticker_id,
            "symbol": h["symbol"],
            "name": h["name"],
            "underlying": h.get("underlying") or h["name"] or h["symbol"],
            "currency": currency,
            "shares": round(shares, 4),
            "avg_cost_native": round(avg_cost_native, 4),
            "current_price_native": round(current_price, 4),
            "value_native": round(value_native, 2),
            "value_sgd": round(value_sgd, 2),
            "total_pl_native": round(total_pl_native, 2),
            "total_pl_sgd": round(total_pl_sgd, 2),
            "total_pl_pct": round(total_pl_pct, 2),
            "daily_pl_native": round(daily_pl_native, 2),
            "daily_pl_sgd": round(daily_pl_sgd, 2),
            "daily_pl_pct": round(daily_pl_pct, 2)
        })
        
    # Sort holdings by value descending
    holdings_list.sort(key=lambda x: x["value_sgd"], reverse=True)
    
    # 6. Aggregate portfolio-level performance metrics
    total_unrealized_pl_sgd = total_value_sgd - total_cost_sgd
    total_unrealized_pl_pct = (total_unrealized_pl_sgd / total_cost_sgd * 100) if total_cost_sgd > 0 else 0.0
    
    aggregate_daily_pl_pct = (total_daily_pl_sgd / total_prev_close_value_sgd * 100) if total_prev_close_value_sgd > 0 else 0.0
    
    # Calculate total transaction fees/commissions paid in SGD using historical rates
    total_fees_sgd = 0.0
    for pid in portfolio_ids:
        cursor.execute("""
            SELECT commission, currency, date
            FROM transactions
            WHERE portfolio_id = ? AND commission > 0
        """, (pid,))
        fee_rows = cursor.fetchall()
        for fee_row in fee_rows:
            fee_amount = fee_row['commission'] or 0.0
            currency = fee_row['currency']
            date_str = fee_row['date']
            rate = get_historical_exchange_rate(date_str, currency, conn)
            total_fees_sgd += fee_amount * rate

    total_dividend_taxes_sgd = total_dividends_gross_sgd - total_dividends_net_sgd
    
    # Total Profit is: Capital Gain (Unrealized) + Realized P&L + Gross Dividends - Taxes - Fees
    total_profit_sgd = total_unrealized_pl_sgd + total_realized_pl_sgd + total_dividends_net_sgd - total_fees_sgd
    
    return {
        "portfolio_id": portfolio_id,
        "portfolio_name": portfolios[0]['name'] if (portfolio_id is not None and portfolios) else "My Net Worth",
        "total_value_sgd": round(total_value_sgd, 2),
        "total_cost_sgd": round(total_cost_sgd, 2),
        "total_unrealized_pl_sgd": round(total_unrealized_pl_sgd, 2),
        "total_unrealized_pl_pct": round(total_unrealized_pl_pct, 2),
        "total_daily_pl_sgd": round(total_daily_pl_sgd, 2),
        "total_daily_pl_pct": round(aggregate_daily_pl_pct, 2),
        "total_dividends_gross_sgd": round(total_dividends_gross_sgd, 2),
        "total_dividends_net_sgd": round(total_dividends_net_sgd, 2),
        "total_dividend_taxes_sgd": round(total_dividend_taxes_sgd, 2),
        "total_fees_sgd": round(total_fees_sgd, 2),
        "total_realized_pl_sgd": round(total_realized_pl_sgd, 2),
        "total_profit_sgd": round(total_profit_sgd, 2),
        "holdings": holdings_list,
        "monthly_dividends": {k: round(v, 2) for k, v in monthly_dividends.items()}
    }

def get_shares_on_date(portfolio_id: int, ticker_id: int, date_str: str, conn) -> float:
    """
    Chronologically processes all transactions for a specific portfolio and ticker
    up to date_str and returns the quantity of shares held.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT action, quantity, price
        FROM transactions
        WHERE portfolio_id = ? AND ticker_id = ? AND date(date) <= date(?)
        ORDER BY date ASC, 
                 CASE action 
                    WHEN 'BUY' THEN 1 
                    WHEN 'SPLIT' THEN 2 
                    WHEN 'SELL' THEN 3 
                    ELSE 4 
                 END ASC, 
                 id ASC
    """, (portfolio_id, ticker_id, date_str))
    
    shares = 0.0
    for row in cursor.fetchall():
        action = row['action'].upper()
        quantity = float(row['quantity'])
        price = float(row['price'])
        if action == 'BUY':
            shares += quantity
        elif action == 'SELL':
            shares -= quantity
            if shares < 0.00001:
                shares = 0.0
        elif action == 'SPLIT':
            ratio = price
            if ratio > 0:
                shares = shares * ratio
    return shares

