from typing import Any
from pydantic import BaseModel, Field, RootModel

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
    tags: list[str] | None = None
    underlying: str | None = None
    classification: str | None = None
    category: str | None = None
    subclass: str | None = None
    exchange: str | None = None
    price: float | None = None
    is_manual: bool | int | None = None

class TagCreate(BaseModel):
    name: str
    color: str | None = "#3b82f6"

class ManualPriceOverride(BaseModel):
    symbol: str | None = None
    ticker_id: int | None = None
    price: float
    date: str | None = None

class ManualPriceDetailOverride(BaseModel):
    symbol: str | None = None
    ticker_id: int | None = None
    date: str
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None = None
    is_manual: int = 1

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

class SystemdTriggerRequest(BaseModel):
    action: str
    qty: float | None = None
    notes: str | None = None

class PortfoliosReorder(BaseModel):
    order: list[int]

class CashMetricCreate(BaseModel):
    date: str = Field(
        ...,
        description="Metric date in YYYY-MM-DD format (if on/after NY today, automatically aligns to current trading day)",
        examples=["2026-09-04"]
    )
    broker: str = Field(
        ...,
        description="Broker identifier (e.g. IBKR, MOOMOO, SRS, CDP)",
        examples=["IBKR"]
    )
    liquidation_value: float = Field(
        ...,
        description="Total net liquidation account value in SGD",
        examples=[125450.75]
    )
    total_stock_value: float = Field(
        ...,
        description="Total market value of equities/stocks held in SGD",
        examples=[102300.50]
    )
    cash_on_hand: float = Field(
        ...,
        description="Uninvested settled cash balance on hand in SGD",
        examples=[23150.25]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2026-09-04",
                "broker": "IBKR",
                "liquidation_value": 125450.75,
                "total_stock_value": 102300.50,
                "cash_on_hand": 23150.25
            }
        }
    }

class CashMetricItem(BaseModel):
    date: str = Field(..., description="Trading date in YYYY-MM-DD format", examples=["2026-09-04"])
    broker: str = Field(..., description="Broker identifier", examples=["IBKR"])
    liquidation_value: float = Field(..., description="Liquidation value in SGD", examples=[125450.75])
    base_capital: float | None = Field(default=0.0, description="Cumulative base capital in SGD", examples=[100000.00])
    total_stock_value: float = Field(..., description="Total stock value in SGD", examples=[102300.50])
    cash_on_hand: float = Field(..., description="Cash on hand in SGD", examples=[23150.25])

class CashMetricLastItem(BaseModel):
    liquidation_value: float = Field(..., description="Latest liquidation value in SGD", examples=[125450.75])
    total_stock_value: float = Field(..., description="Latest total stock value in SGD", examples=[102300.50])
    cash_on_hand: float = Field(..., description="Latest cash on hand in SGD", examples=[23150.25])
    date: str = Field(..., description="Date of latest record in YYYY-MM-DD format", examples=["2026-09-04"])

class StatusResponse(BaseModel):
    status: str = Field(..., description="Status outcome string", examples=["success"])
    message: str | None = Field(default=None, description="Optional informational message", examples=["Operation completed successfully."])

class CapitalEntryCreate(BaseModel):
    date: str = Field(
        ...,
        description="Date of deposit or withdrawal in YYYY-MM-DD format",
        examples=["2026-09-01"]
    )
    broker: str = Field(
        ...,
        description="Broker identifier (e.g. IBKR, MOOMOO, SRS, CDP)",
        examples=["IBKR"]
    )
    amount: float = Field(
        ...,
        description="Capital amount in SGD (positive for deposit, negative for withdrawal)",
        examples=[5000.00]
    )
    remarks: str | None = Field(
        default="",
        description="Optional notes or reference regarding this capital entry",
        examples=["Monthly DCA deposit"]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2026-09-01",
                "broker": "IBKR",
                "amount": 5000.00,
                "remarks": "Monthly DCA deposit"
            }
        }
    }

class CapitalEntryItem(BaseModel):
    id: int = Field(..., description="Unique entry ID", examples=[1])
    date: str = Field(..., description="Date of capital entry in YYYY-MM-DD format", examples=["2026-09-01"])
    broker: str = Field(..., description="Broker identifier", examples=["IBKR"])
    amount: float = Field(..., description="Capital amount in SGD", examples=[5000.00])
    remarks: str | None = Field(default="", description="Remarks or notes", examples=["Monthly DCA deposit"])

class CashMetricsUploadPayload(BaseModel):
    liquidation_value: float | None = Field(default=None, description="Net liquidation value in SGD", examples=[125450.75])
    total_stock_value: float | None = Field(default=None, description="Total stock value in SGD", examples=[102300.50])
    cash_on_hand: float | None = Field(default=None, description="Cash balance on hand in SGD", examples=[23150.25])
    NetLiquidation: float | None = Field(default=None, description="IBKR alias for net liquidation value", examples=[125450.75])
    GrossPositionValue: float | None = Field(default=None, description="IBKR alias for gross position/stock value", examples=[102300.50])
    TotalCashValue: float | None = Field(default=None, description="IBKR alias for total cash on hand", examples=[23150.25])
    balances: dict[str, float] | None = Field(default=None, description="Optional nested balances dictionary")

    model_config = {
        "json_schema_extra": {
            "example": {
                "liquidation_value": 125450.75,
                "total_stock_value": 102300.50,
                "cash_on_hand": 23150.25
            }
        }
    }




