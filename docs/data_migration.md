# Data Migration Guide: Snowball Analytics to Self-Hosted Portfolio Manager

This guide describes how to export your historical investment data from Snowball Analytics and import it cleanly into the Self-Hosted Portfolio Manager.

---

## 1. Exporting Data from Snowball Analytics

To migrate your portfolios, you must export two CSV files for each portfolio: **Holdings** and **Transactions**.

### 1.1 Holdings Data Export
1. Log into your Snowball Analytics account.
2. Navigate to **Portfolio** > **Holdings**.
3. Locate the **"Export to CSV"** button (usually at the top right of the holdings list table).
4. Click the button to download the holdings CSV.
5. Save the file with a descriptive name (e.g. `my-portfolio-holdings.csv`).

### 1.2 Transactions Data Export
1. In Snowball Analytics, navigate to **Portfolio** > **Transactions**.
2. Click the **"Export"** or **"Export to CSV"** button.
3. Save this file as well (e.g. `my-portfolio-transactions.csv`).

---

## 2. Ingesting Data into the Portfolio Manager

To import your files:
1. Open the Portfolio Manager dashboard in your browser.
2. Open the **Import Portfolios** wizard/modal in the navigation controls.
3. Enter the target **Portfolio Name** (e.g., *Income Factory*, *MooMoo*).
4. Upload your exported holdings CSV and transactions CSV.
5. Click **Import**. The application will automatically parse, normalize, compute FIFO cost bases, sync current prices from Yahoo Finance, and refresh the dashboard.

---

## 3. Notes & Troubleshooting
* **UTF-8 BOM**: The importer automatically handles UTF-8 Byte Order Marks (BOMs) exported by Excel.
* **Return of Capital / Option Premiums**: Events matching `OTHER_INCOME` or Return of Capital (ROC) are automatically converted into tax-deducted dividend entries.
* **Same-Day Priority**: If a `BUY` and a `SELL` transaction occur on the same day, the parser chronologically groups `BUY` and `SPLIT` operations first to prevent transient negative share balance errors.

---

## 4. Expected CSV Import Formats

The ingestion engine processes files matching the formats exported directly from Snowball Analytics:

### 4.1 Holdings CSV (e.g., `snowball-holdings.csv`)
Expected headers:
`Holding, Holdings' name, Note, Shares, Currency, Share price, Country, Portfolios`
* `Holding`: Ticker symbol (e.g. `AAPL`, `D05.SI`).
* `Holdings' name`: Friendly display name.
* `Currency`: Asset denomination currency (e.g. `USD`, `SGD`, `CAD`).
* `Shares`: Holding position count.
* `Share price`: Current price per share (reference price).
* `Note`: Description or notes (used for parsing custom subclasses/categories).
* `Portfolios`: comma-separated lists of portfolio names matching this holding.

### 4.2 Transactions CSV (e.g., `snowball-transactions.csv`)
Expected headers:
`Event, Date, Symbol, Price, Quantity, Currency, FeeTax, Exchange, Note`
* `Event`: Transaction action. Allowed values: `BUY`, `SELL`, `SPLIT`, `DIVIDEND`, `OTHER_INCOME`, `FEE`.
  - **BUY / SELL / SPLIT**: Triggers cost-basis and portfolio holdings calculation.
  - **DIVIDEND / OTHER_INCOME** (like Return of Capital / option premiums): Imported as cash distributions inside dividends.
* `Date`: Date of trade (format: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`).
* `Symbol`: Ticker symbol (e.g., `NVDA`).
* `Price`: Price per share.
* `Quantity`: Trade volume (amount of shares).
* `FeeTax`: Transaction fees or withholding taxes.
* `Exchange`: Market exchange (e.g. `NASDAQ`, `SGX`).
* `Note`: Developer descriptions or tags.




