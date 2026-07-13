from pydantic import BaseModel

class PortfolioCreate(BaseModel):
    name: str
    classification: str | None = None
    broker: str | None = None

class PortfolioUpdate(BaseModel):
    name: str
    classification: str | None = None
    broker: str | None = None

class TickerUpdate(BaseModel):
    friendly_name: str | None = None
    tax_rate: float | None = None
    notes: str | None = None
    underlying: str | None = None
    classification: str | None = None
    category: str | None = None
    subclass: str | None = None
    exchange: str | None = None

class TransactionCreate(BaseModel):
    portfolio_id: int
    ticker: str        # Ticker symbol
    date: str          # YYYY-MM-DD HH:MM:SS or YYYY-MM-DD
    action: str        # 'BUY', 'SELL', 'SPLIT'
    price: float
    quantity: float
    currency: str      # 'USD', 'SGD', 'CAD'
    commission: float = 0.0
    exchange: str | None = None
    notes: str | None = None

class DividendCreate(BaseModel):
    portfolio_id: int
    ticker: str        # Ticker symbol
    date: str
    amount: float
    currency: str
    tax: float | None = None  # If None, auto-calculated from ticker tax rate
    qty: float | None = None
    notes: str | None = None

class PortfoliosReorder(BaseModel):
    order: list[int]
