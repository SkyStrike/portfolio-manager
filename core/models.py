import re
from datetime import datetime

# --- Utilities ---

def parse_val(val_str):
    """Sanitizes currency and percentage strings into float numbers."""
    if not val_str:
        return 0.0
        
    sanitized = val_str.strip().replace('$', '').replace(',', '').replace('%', '').strip()
    if not sanitized or sanitized == '-':
        return 0.0
        
    try:
        return float(sanitized)
    except ValueError:
        return 0.0

def format_qty(qty):
    """Formats quantity to 4 decimal places for high-precision assets."""
    return f"{qty:,.4f}".rstrip('0').rstrip('.')

def slugify(text):
    """Generates URL-safe IDs for HTML anchors and TOC linking."""
    text = text.lower()
    text = re.sub(r'[^\w\s\-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

# --- Data Models ---

class Position:
    """
    Central logic for a single ticker.
    Calculates lifetime ROI, capital gains, and SGD equivalents.
    """
    def __init__(self, symbol, ticker_info, rate):
        self.symbol = symbol
        self.rate = rate  # Conversion rate to SGD
        self.underlying = ticker_info.get('underlying', symbol)
        self.classification = ticker_info.get('classification', 'Other')
        self.category = ticker_info.get('category') or ticker_info.get('subclass') or 'Other'
        self.exchange = ticker_info.get('exchange')
        
        self.transactions = []
        self.income_records = []
        self.market_value = 0.0
        self.daily_val = 0.0
        self.daily_pct = 0.0
        self.currency = "SGD"
        self.is_augmented = False
        self.ib_mismatch = False
        self.ib_actual_qty = None
        self.ibkr_calc_qty = None

    @property
    def subclass(self):
        return self.category

    @subclass.setter
    def subclass(self, value):
        self.category = value

    def add_transaction(self, tx):
        self.transactions.append(tx)
        self.currency = tx['currency']

    def add_income(self, inc):
        self.income_records.append(inc)
        self.currency = inc['currency']

    @property
    def current_quantity(self):
        return sum(
            tx['qty'] if tx['action'] == 'Buy' else -tx['qty'] 
            for tx in self.transactions
        )

    @property
    def is_closed(self):
        return abs(self.current_quantity) < 0.000001

    @property
    def total_buy_cost(self):
        return sum(
            tx['qty'] * tx['price'] 
            for tx in self.transactions 
            if tx['action'] == 'Buy'
        )

    @property
    def total_buy_quantity(self):
        return sum(
            tx['qty'] 
            for tx in self.transactions 
            if tx['action'] == 'Buy'
        )

    @property
    def total_sell_proceeds(self):
        return sum(
            tx['qty'] * tx['price'] 
            for tx in self.transactions 
            if tx['action'] == 'Sell'
        )

    @property
    def total_fees(self):
        return sum(tx.get('fee', 0.0) for tx in self.transactions)

    @property
    def total_net_income(self):
        return sum(inc['net'] for inc in self.income_records)

    @property
    def average_buy_price(self):
        shares = 0.0
        avg_cost = 0.0
        for tx in self.transactions:
            action = tx['action']
            qty = tx['qty']
            price = tx['price']
            if action == 'Buy':
                new_shares = shares + qty
                if new_shares > 0:
                    avg_cost = (shares * avg_cost + qty * price) / new_shares
                shares = new_shares
            elif action == 'Sell':
                shares = max(0.0, shares - qty)
                if shares <= 1e-6:
                    shares = 0.0
                    avg_cost = 0.0
            elif action == 'Split':
                ratio = price
                if ratio > 0:
                    shares *= ratio
                    avg_cost /= ratio
        return avg_cost

    @property
    def cost_basis(self):
        """Calculates basis based on currently held shares (Active) or total historical (Closed)."""
        if self.is_closed:
            return self.total_buy_cost
        return self.current_quantity * self.average_buy_price

    @property
    def exit_or_current_value(self):
        if self.is_closed:
            return self.total_sell_proceeds
        return self.market_value

    @property
    def capital_gain(self):
        return self.exit_or_current_value - self.cost_basis

    @property
    def realized_pnl(self):
        """Profit/Loss from shares already sold."""
        active_basis = 0.0 if self.is_closed else (self.current_quantity * self.average_buy_price)
        cost_of_shares_sold = self.total_buy_cost - active_basis
        return self.total_sell_proceeds - cost_of_shares_sold

    @property
    def realized_pnl_sgd(self):
        return self.realized_pnl * self.rate

    @property
    def capital_gain_sgd(self):
        return self.capital_gain * self.rate

    @property
    def lifetime_profit(self):
        """Total returns including market movement, dividends, and fees."""
        revenue = self.market_value + self.total_sell_proceeds + self.total_net_income
        costs = self.total_buy_cost + self.total_fees
        return revenue - costs

    # --- SGD Conversion Helpers ---
    @property
    def invested_sgd(self): 
        return self.cost_basis * self.rate
        
    @property
    def current_sgd(self): 
        if self.is_closed:
            return 0.0
        return self.market_value * self.rate

    @property
    def daily_val_sgd(self):
        return self.daily_val * self.rate
        
    @property
    def current_price(self):
        qty = self.current_quantity
        if qty <= 0:
            return 0.0
        return self.market_value / qty

    @property
    def income_sgd(self): 
        return self.total_net_income * self.rate
        
    @property
    def fees_sgd(self): 
        return self.total_fees * self.rate
        
    @property
    def total_returns(self):
        """Calculates total outcome: Current Value + Income - Fees."""
        return self.market_value + self.total_net_income - self.total_fees

    @property
    def total_returns_sgd(self):
        return self.total_returns * self.rate

    @property
    def profit_sgd(self): 
        return self.lifetime_profit * self.rate

    @property
    def latest_tx_date(self):
        if not self.transactions: return None
        return max(t['date'] for t in self.transactions)

    @property
    def earliest_buy_date(self):
        buy_txs = [tx['date'] for tx in self.transactions if tx['action'] == 'Buy']
        if not buy_txs:
            return None
        return min(buy_txs)

    def get_roi_percentage(self):
        basis = self.total_buy_cost if self.is_closed else self.cost_basis
        if basis <= 0:
            return 0.0
        return (self.lifetime_profit / basis) * 100

    def get_capital_gain_percentage(self):
        basis = self.total_buy_cost if self.is_closed else self.cost_basis
        if basis <= 0:
            return 0.0
        return (self.capital_gain / basis) * 100

    def to_dict(self):
        """Serializes the position for the JSON export used by the renderer."""
        if self.earliest_buy_date:
            dt_start = datetime.strptime(self.earliest_buy_date, '%Y-%m-%d')
            days = (datetime.now() - dt_start).days
        else:
            days = 0
            
        roi = self.get_roi_percentage()
        
        if days > 0:
            avg_annual_roi = (roi / days) * 365
        else:
            avg_annual_roi = 0.0

        from collections import defaultdict
        income_by_year = defaultdict(list)
        for r in self.income_records:
            year = r.get('year')
            if year:
                income_by_year[year].append(r)

        yearly_summaries = {}
        for Y in sorted(income_by_year.keys(), reverse=True):
            total_net = sum(r['net'] for r in income_by_year[Y])
            total_gross = sum(r['amt'] for r in income_by_year[Y])
            total_tax = sum(r['tax'] for r in income_by_year[Y])
            
            # Shift ROC collected in Y+1 to year Y
            try:
                next_year = str(int(Y) + 1)
            except:
                next_year = ""
            roc_amount = 0.0
            if next_year:
                roc_amount = sum(
                    r['net'] for r in income_by_year.get(next_year, []) 
                    if 'ROC' in r.get('note', '').strip().upper() or 
                       'RETURN OF CAPITAL' in r.get('note', '').strip().upper()
                )
            
            roc_pct = (roc_amount / total_tax * 100) if total_tax > 0 else 0.0
            actual_tax_rate = (100.0 - roc_pct) * 0.3
            actual_tax_value = total_tax - roc_amount
            
            yearly_summaries[Y] = {
                "total_net": total_net,
                "total_gross": total_gross,
                "total_tax": total_tax,
                "roc_amount": roc_amount,
                "roc_pct": roc_pct,
                "actual_tax_rate": actual_tax_rate,
                "actual_tax_value": actual_tax_value
            }
            
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "underlying": self.underlying,
            "classification": self.classification,
            "category": self.category,
            "subclass": self.category,
            "currency": self.currency,
            "is_closed": self.is_closed,
            "rate": self.rate,
            "is_augmented": self.is_augmented,
            "ib_mismatch": getattr(self, "ib_mismatch", False),
            "ib_actual_qty": getattr(self, "ib_actual_qty", None),
            "ibkr_calc_qty": getattr(self, "ibkr_calc_qty", None),
            "ib_cost_basis": getattr(self, "ib_cost_basis", None),
            "ib_unrealized_profits": getattr(self, "ib_unrealized_profits", None),
            "ib_market_value": getattr(self, "ib_market_value", None),
            "ib_current_price": getattr(self, "ib_current_price", None),
            "yearly_income_summaries": yearly_summaries,
            "price_details": getattr(self, "price_details", None),
            "metrics": {
                "quantity": self.current_quantity,
                "average_buy_price": self.average_buy_price,
                "cost_basis": self.cost_basis,
                "market_value": self.market_value,
                "daily_val": self.daily_val,
                "daily_pct": self.daily_pct,
                "current_price": self.current_price,
                "capital_gain": self.capital_gain,
                "capital_gain_pct": self.get_capital_gain_percentage(),
                "realized_pnl": self.realized_pnl,
                "dividends_net": self.total_net_income,
                "dividends_gross": sum(r['amt'] for r in self.income_records),
                "dividends_tax": sum(r['tax'] for r in self.income_records),
                "total_fees": self.total_fees,
                "lifetime_profit": self.lifetime_profit,
                "total_returns": self.total_returns,
                "roi_pct": roi,
                "days_since_first_tx": days,
                "latest_tx_date": self.latest_tx_date,
                "avg_returns_per_year": avg_annual_roi,
                "capital_gain_sgd": self.capital_gain_sgd,
            },
            "sgd_metrics": {
                "invested_sgd": self.invested_sgd,
                "current_sgd": self.current_sgd,
                "daily_val_sgd": self.daily_val_sgd,
                "income_sgd": self.income_sgd,
                "fees_sgd": self.fees_sgd,
                "realized_pnl_sgd": self.realized_pnl_sgd,
                "profit_sgd": self.profit_sgd,
                "total_returns_sgd": self.total_returns_sgd,
            },
            "transactions": self.transactions,
            "income": self.income_records
        }
