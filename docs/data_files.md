# Data Files Directory & JSON Schema Reference

This document provides a detailed catalog of the various JSON configuration, cache, and import data files used throughout the Self-Hosted Portfolio Manager application, including their purpose, structural details, and JSON schemas.

---

## Index of Key JSON & XML Files

1. [config/config.json (Main System Configuration)](#1-configconfigjson-main-system-configuration)
2. [data/ib_data.json (IBKR live portfolio positions cache)](#2-dataib_datajson-ibkr-live-portfolio-positions-cache)

---

### 1. `config/config.json` (Main System Configuration)
* **Purpose**: Declares core system constants, UI parameters, currency conversion rates, file paths for dynamic document uploads, and API integration paths.
* **Storage Location**: Located under `config/config.json` (default template). User overrides are uploaded or saved to `data/config.json` (which takes precedence).
* **Schema & Structure**:
```json
{
  "brokers": [ "IBKR", "MOOMOO" ],
  "finance": {
    "max_workers": 30,
    "conversion_rates": {
      "USD": 1.2754,
      "CAD": 0.9327,
      "SGD": 1.0
    }
  },
  "ui": {
    "page_width": "1800px",
    "chart_height": "40vh",
    "font_size": "1em",
    "mobile_font_size": "0.8em",
    "colors": {
      "invested": "#7f8c8d",
      "current": "#3498db",
      "returns": "#2ecc71",
      "income": "#2ecc71",
      "positive": "#3498db",
      "negative": "#e74c3c"
    }
  },
  "allowed_documents": {
    "stock-options": "data/stock-options.json",
    "ib-data": "data/ib_data.json"
  },
  "external_services": {
    "options_tracker_url": "",
    "backtester_url": ""
  }
}
```

---

### 2. `data/ib_data.json` (IBKR Live Portfolio Positions Cache)
* **Purpose**: Caches the live inventory data retrieved from IBKR reports, including margin requirements, cash, and open asset lot metrics. Used as fallback data when Yahoo Finance is offline or fetching stock price definitions.
* **Storage Location**: Uploaded or synchronized to `data/ib_data.json`.
* **Schema & Structure**:
```json
{
  "metadata": {
    "generated_datetime": "2026-07-06T09:50:34.666319"
  },
  "balances": {
    "FullInitMarginReq": 136718.05,
    "FullMaintMarginReq": 132829.28,
    "GrossPositionValue": 427190.98,
    "InitMarginReq": 136718.05,
    "LookAheadInitMarginReq": 136718.05,
    "MaintMarginReq": 132829.28,
    "NetLiquidation": 441830.31,
    "PostExpirationMargin": 0.0,
    "TotalCashValue": 19289.11
  },
  "portfolio": [
    {
      "symbol": "ADEA",
      "description": "ADEA",
      "type": "STK",
      "exchange": "NASDAQ",
      "position": 40.0,
      "cost_basis": 25.94766,
      "current_price": 29.20,
      "market_value": 1168.0,
      "unrealized_pnl": 130.09,
      "realized_pnl": 0.0
    }
  ]
}
```