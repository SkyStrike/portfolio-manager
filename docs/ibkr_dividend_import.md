# IBKR Dividend Import Guide

This guide documents the integration of Interactive Brokers (IBKR) dividend transactions and data reconciliation in the Portfolio Manager.

---

## 1. How IBKR Dividend Importing Works

The dividend import processes transaction reports directly from Interactive Brokers in-memory without saving temporary source files to disk.
1. **Flex Query Extraction**: Official Flex Query reports (XML format) are downloaded from IBKR.
2. **Direct Import Ingestion**: The raw XML file is uploaded directly to the `/api/dividends/import-ibkr` endpoint using a multipart form request. (A custom JSON format is supported by the API for advanced programmatic users, but is not natively selectable in the GUI).
3. **In-Memory Parsing**: The backend parses the XML structure in-memory, filters dividends within the designated date range, resolves portfolios, and inserts reconciled entries directly into the SQLite database.

> [!NOTE]
> The automated Flex Query downloader service is currently Work in Progress (WIP). In the meantime, dividends can be added or updated manually via the **Transactions & Dividends** ledger interface or uploaded via CSV inputs.

---

## 2. Triggering the Import via API

> [!IMPORTANT]
> The IBKR dividend import is strictly intended for portfolios with `broker = 'IBKR'`.

> [!IMPORTANT]
> The script attempts to calculate/fetch the quantity/share count based on the settle date. There could be inaccuracies stemmed from purchase of stocks after ex-dividend date and before payment date(settle date). These entries needs to be updated manually. But overall, it does not affect the calculation of the dividends. But it will affect how the dividend per share is reflected for the stock.

When importing entries, the manager resolves the target portfolio for each dividend record using the following priority:
1. **Existing Ticker Lookup**: The API looks up existing transaction records across all portfolios configured with `broker = 'IBKR'`. If a ticker symbol already exists in one of these portfolios, the dividend is automatically routed to that portfolio. If the symbol is held across multiple IBKR portfolios, the importer routes it to the portfolio containing the most recent transaction for that symbol.
2. **Portfolio Parameter Fallback**: If the ticker is missing from transaction records entirely, the importer falls back to the target portfolio specified in the `portfolio` query parameter.

* **Endpoint**: `POST /api/dividends/import-ibkr`
* **Query Parameters**:
  - `start_date`: Settle date range start (format: `YYYY-MM-DD`).
  - `end_date`: Settle date range end (format: `YYYY-MM-DD`).
  - `portfolio`: Fallback target portfolio name (defaults to `"income factory"`).
* **Payload Parameters**:
  - `file` (Multipart File): XML file (or custom JSON file for advanced users) containing IBKR dividend transactions.

### Example `curl` Command with Direct XML File:
```bash
curl -X POST "http://localhost:8080/api/dividends/import-ibkr?start_date=2026-01-01&end_date=2026-06-30&portfolio=Income%20Factory" \
  -F "file=@/path/to/dividend-ytd.xml"
```

### Reference XML Schema Format:
The uploaded `.xml` file must contain `<CashTransaction>` elements inside `<CashTransactions>` tags matching this structure:
```xml
<FlexQueryResponse queryName="dividend-ytd" type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U11188800" fromDate="20260101" toDate="20260703" period="YearToDate">
      <CashTransactions>
        <CashTransaction 
          accountId="U11188800" 
          currency="CAD" 
          fxRateToBase="0.92515" 
          assetCategory="STK" 
          subCategory="ETF" 
          symbol="AMDY" 
          description="AMDY(CA4175171095) CASH DIVIDEND CAD 0.45 PER SHARE" 
          underlyingSymbol="AMDY" 
          dateTime="20260106;202000" 
          settleDate="20260106" 
          amount="-33.75" 
          type="Withholding Tax" 
          transactionID="901528624" 
          reportDate="20260107" 
        />
        <CashTransaction 
          accountId="U11188800" 
          currency="CAD" 
          fxRateToBase="0.92515" 
          assetCategory="STK" 
          subCategory="ETF" 
          symbol="AVGY" 
          description="AVGY(CA41757J1075) CASH DIVIDEND CAD 0.48 PER SHARE" 
          underlyingSymbol="AVGY" 
          dateTime="20260106;202000" 
          settleDate="20260106" 
          amount="72.0" 
          type="Dividends" 
          transactionID="901528238" 
          reportDate="20260107" 
        />
      </CashTransactions>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>
```

### Reference JSON Schema Format:
** basically an array of xml items without the xml container elements

```json
[
    {
        "accountId": "U11188800",
        "currency": "CAD",
        "fxRateToBase": "0.92515",
        "assetCategory": "STK",
        "subCategory": "ETF",
        "symbol": "AMDY",
        "description": "AMDY(CA4175171095) CASH DIVIDEND CAD 0.45 PER SHARE - CA TAX",
        "underlyingSymbol": "AMDY",
        "dateTime": "20260106;202000",
        "settleDate": "20260106",
        "amount": "-33.75",
        "type": "Withholding Tax",
        "dividendType": "",
        "transactionID": "691528624",
        "reportDate": "20260107",
        "exDate": ""
    },
    {
        "accountId": "U11188800",
        "currency": "CAD",
        "fxRateToBase": "0.92515",
        "assetCategory": "STK",
        "subCategory": "ETF",
        "symbol": "AVGY",
        "description": "AVGY(CA41757J1075) CASH DIVIDEND CAD 0.48 PER SHARE - CA TAX",
        "underlyingSymbol": "AVGY",
        "dateTime": "20260106;202000",
        "settleDate": "20260106",
        "amount": "-36",
        "type": "Withholding Tax",
        "dividendType": "",
        "transactionID": "691528238",
        "reportDate": "20260107",
        "exDate": ""
    }
    ...
]
```
