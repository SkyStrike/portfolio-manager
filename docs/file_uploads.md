# File Upload API Guide

This guide documents how to securely upload supplemental configuration files and data reports into the Portfolio Manager using the document upload API.

---

## 1. Document Types & Target Paths

The generic `/api/upload` endpoint accepts uploads for files mapped inside `config/config.json`'s `allowed_documents` section. The standard supported keys include:

| `document_type` | Destination Path | Description |
| :--- | :--- | :--- |
| **`stock-options`** | `data/stock-options.json` | Active options trades, strikes, expiries, and premium metrics. |
| **`ib-data`** | `data/ib_data.json` | Active stock holdings and balances (NetLiquidation, GrossPositionValue, TotalCashValue) reported directly by IBKR for verification and cash reports. |


---

## 2. API Endpoint Specification

### `POST /api/upload`

Uploads a document to the server. The server automatically validates file formats (such as XML parsing validation for `.xml` files, or JSON parsing validation for `.json` files) before writing the file.

* **Payload Format**: `multipart/form-data`
* **Form Parameters**:
  - `document_type`: Must match one of the string keys listed in the mapping above.
  - `file`: The local file binary stream.

---

## 3. Usage Examples (`curl`)

Make sure to prepend the `${BASE_PATH}` prefix to the URL if the application is hosted under a reverse-proxy path (e.g. `http://localhost:8080/portfolio/api/upload`).

### 3.1 Uploading an IBKR Portfolio Report (`ib-data`)
```bash
curl -X POST http://localhost:8080/api/upload \
  -F "document_type=ib-data" \
  -F "file=@/path/to/ib_data.json"
```


---

## 4. Behavior & Automation

* **Integrity Validation**: If a `.json` format destination is selected, the server will attempt to load and parse the file binary as JSON before accepting it. If parsing fails, the upload will reject with an HTTP `400 Bad Request` code and describe the syntax error.
* **Automatic Rebuild**: A successful upload immediately triggers an **asynchronous dashboard rebuild** task (`rebuild_all_views`) in the background. The new holdings details, options sheets, or cash graphs will reflect on the UI within a few seconds without restarting the container.
