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

### Explanation of Attributes & Usage

#### Core Attributes
* **`brokers`** (array of strings): Defines the list of active brokers supported in system drop-downs and portfolio configurations (e.g. `["IBKR", "MOOMOO"]`). Adding a broker here registers it across editing interfaces.

#### Finance Parameters
* **`finance.max_workers`** (integer): Sets the maximum number of concurrent threads/workers utilized by the background `yfinance` price updates. Higher values fetch tickers in parallel faster but can cause rate-limiting issues.
* **`finance.conversion_rates`** (object): Mapping of conversion rates relative to SGD (e.g., `USD: 1.2754` meaning $1$ USD = $1.2754$ SGD). These act as fallback exchange rates if the dynamic API fetching tool is offline.

#### UI Customization
* **`ui.page_width`** (CSS string): Declares the desktop container constraint wrapper size.
* **`ui.chart_height`** (CSS string): Sets the viewport height for the ChartJS rendering frames on the dashboard.
* **`ui.font_size`** & **`ui.mobile_font_size`** (CSS strings): Scales base HTML REM sizing dynamically for responsive UI displays.
* **`ui.colors`** (hex codes): Color tags mapping to metric cards:
  * `invested`: Colors representing original cost capital invested.
  * `current`: Colors representing current MTM value of holdings.
  * `returns` & `income`: Accent colors for gains and dividend aggregations.
  * `positive` & `negative`: Profit (gain) and loss colors used globally.

#### Allowed Documents Map
* **`allowed_documents`** (key-value object): Maps internal lookup identifiers to actual filesystem storage paths on disk. Used by the upload API (`POST /api/upload`) to validate target file writes (e.g., writing the `ib-data` payload directly to `data/ib_data.json`).

#### External Integrations
* **`external_services.options_tracker_url`** (string): The HTTP address of the companion options tracker. If configured, activates option lists and cash stress test components. If left empty (`""`), all options components are dynamically hidden from the UI.
* **`external_services.backtester_url`** (string): The HTTP address of the companion backtesting service. If populated, renders direct link icons (🔗) next to assets pointing to historical backtests.

---

### 2. `data/ib_data.json` (IBKR Live Portfolio Positions Cache)
* **Purpose**: Caches the live inventory data retrieved from IBKR reports, including margin requirements, cash, and open asset lot metrics. Used as fallback data when Yahoo Finance is offline or fetching stock price definitions.
* **Detailed Guide**: For a complete breakdown of this file's attributes, ingestion parameters, custom extraction scripts, and GUI setup details, see the **[IBKR Data File Guide (ib_data.json)](ib_data_guide.md)**.
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