# System Maintenance, Patching & Backups Guide

This guide explains how to use, configure, and author patches for the self-hosted portfolio manager, as well as how to perform database backup and restore operations directly from the Control Center.

---

## 1. Database Backup & Restore

The application supports hot-swap backups and restores using SQLite's native `sqlite3.backup()` API. 

### How it Works
* **Zero Restarts:** The database connection layer (`core/database.py`) opens and closes file handles on a per-request basis. Because no long-lived global database connections are held in application memory, backups and restores can be performed instantly on a running container without requiring process or container restarts.
* **Storage Location:** All backup files are stored within the persistent `/app/data/` volume on the container, ending in the `.db` extension (e.g. `data/backup_2026_07.db`).

### UI Operations (Control Center > Maintenance)
* **Create Backup:** Input a target backup filename. The system will copy all pages of the active database into the backup file. If the file already exists, it is overwritten.
* **List Backups:** Discovers all `.db` files in the data directory (excluding the active database).
* **Download Backup:** Allows direct downloading of the backup file to your local computer.
* **Delete Backup:** Permanently deletes the backup file from the container volume.
* **Restore Database:** Overwrites the active database (`portfolio.db`) with the contents of the chosen backup file. This operation takes effect immediately for all subsequent HTTP requests. 
  *(Note: Restoring the active database automatically triggers a background cache prewarming/rebuilding task to update the dashboard panels).*


> [!WARNING]
> Data patching is a high-risk operation that directly modifies the database. Extreme caution must be exercised. It is highly recommended to create a database backup before executing any patch.

## 2. Dynamic Patching System

The patching system allows developers to write script-based data patches, declare their input parameters in a JSON manifest, and run them with user-selected inputs from the Control Center UI.

```
patching/
├── 0001/
│   ├── patch_manifest.json    # Declares metadata & UI parameters
│   └── patch_dividends_qty.py  # Contains the patch(params) logic
```

### The Manifest Schema (`patch_manifest.json`)
Every patch must reside in a subfolder inside the `patching/` directory named with a 4-digit sequence (e.g., `0001`, `0002`). This directory must contain a `patch_manifest.json` file defining the parameters that the UI should request from the user.

```json
{
  "id": "0001",
  "name": "Recalculate Dividend Quantities",
  "description": "Calculates and updates missing dividend quantities ('qty' IS NULL) based on holding shares on the dividend payment date.",
  "script": "patch_dividends_qty.py",
  "parameters": []
}
```

#### Parameter Field Definition
For patches requiring inputs, specify them in the `parameters` list:
* `name` (string): Key name passed to the python script.
* `label` (string): Title shown next to the input in the UI.
* `type` (string): Supported types are `string`, `number`, `date`, `boolean`, and `select`.
* `required` (boolean): Enforces browser-level validity checks.
* `default` (any): Initial pre-populated value.
* `options` (array, optional): List of choice values if type is `select`.

*Example with parameters:*
```json
{
  "id": "0002",
  "name": "Adjust Transactions for Stock Split",
  "description": "Adjusts transaction quantities and prices to reflect a stock split event.",
  "script": "adjust_stock_split.py",
  "parameters": [
    {
      "name": "symbol",
      "label": "Stock Symbol",
      "type": "string",
      "required": true
    },
    {
      "name": "split_ratio",
      "label": "Split Ratio (New/Old)",
      "type": "number",
      "required": true,
      "default": 2.0
    },
    {
      "name": "split_date",
      "label": "Split Date",
      "type": "date",
      "required": true
    },
    {
      "name": "dry_run",
      "label": "Dry Run (Preview changes)",
      "type": "boolean",
      "default": true
    }
  ]
}
```

---

## 3. Authoring Python Patch Scripts

Patch scripts are dynamically loaded on-demand by the FastAPI server when triggered from the UI.

### Script Requirements
1. **The Contract Function:** The script must define a `patch(params: dict = None)` function. 
2. **Accessing Parameters:** Values are accessed via the `params` dictionary using the `name` keys defined in the manifest.
3. **Execution Context:** The script runs inside the application's environment. Standard dependencies and database helpers can be imported directly.
4. **Command-Line Compatibility:** To support running the script via command line (e.g. `python3 -m patching.0001.patch_dividends_qty`), wrap the execution call in a `__main__` block.

*Template script:*
```python
import sys
import os

# Ensure the root project directory is in the path when executed directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.database import get_connection

def patch(params: dict = None):
    # Ensure params is initialized
    if params is None:
        params = {}
        
    print("Executing database patch...")
    
    # Read parameters
    dry_run = params.get("dry_run", True)
    symbol = params.get("symbol")
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Perform query/modification operations here
        print(f"Loaded params: dry_run={dry_run}, symbol={symbol}")
    finally:
        conn.close()

if __name__ == '__main__':
    # Fallback params for manual CLI trigger
    patch({"dry_run": False, "symbol": "AAPL"})
```

---

## 4. Troubleshooting & Logging

When a patch is executed via the UI:
1. The backend intercepts Python's standard `stdout` and `stderr` streams.
2. The output of all `print()` statements and full traceback error stacks are captured.
3. This text buffer is returned to the browser and printed instantly on-screen inside the **Console Output Logs** panel.
4. If a script fails, look closely at the console output for SQLite trace logs or Python stack traces.
