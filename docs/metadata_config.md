# Portfolio & Ticker Metadata Configuration Guide

This guide explains how classification, broker designations, and ticker metadata are managed and used in the Portfolio Manager.

---

## 1. Portfolio Metadata

Portfolio attributes are configured in the SQLite database and control how data is segmented and parsed.

### 1.1 `classification`
Categorizes portfolios into distinct groups.
* **Usage**: Used to bundle portfolios on the dashboard and charts. Typical classification groups include:
  - `Income + Growth` (e.g. *Income Factory*, *Long Term Holdings*, *MooMoo*)
  - `Discord` (e.g. *Discord Trades*)
* **Custom Priority**: You can define priority ordering for sorting these sections in the Settings tab of the Admin Dashboard (stored dynamically in the SQLite `settings` table as `sorting.classification_priority`).

### 1.2 `broker`
Maps the holding institution/brokerage.
* **Usage**: Restricts data sync logic. For instance, `data/ib_data.json` checks and overlays are applied strictly to portfolios where the broker is designated as `IBKR`, preventing MooMoo assets from causing false reconciliation mismatches.

---

## 2. Yahoo Finance Symbol Search
Ticker symbols loaded into the database **must be valid yfinance ticker query symbols** to allow automated price syncs.
* **US Stocks**: Use normal symbols (e.g. `AAPL`, `MSFT`).
* **Non-US Exchanges**: Append the appropriate suffix (e.g. `S63.SI` for Singapore Tech Engineering, `SOFY.TO` for Canadian ETFs).
* **Option Contracts**: Standard Yahoo Finance options symbol strings (e.g., `AAPL260619C00200000`) can be mapped directly for automated quote lookups.
