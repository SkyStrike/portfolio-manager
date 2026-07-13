# Interactive Position Calculator User Guide

The **Position Calculator** is a floating multi-ticker utility designed to help you simulate buys, sells, and portfolio adjustments side-by-side in real-time, matching your exact portfolio parameters and denominator boundaries.

---

## 1. Quick Start Guide

### 1.1 Opening the Calculator
1. On the **Active Positions** dashboard page, navigate to any active asset/ticker card.
2. Click the three vertical dots (**`⋮`**) button next to the ticker symbol in the card header to reveal the context menu.
3. Click **🖩 Calculator**. The widget will slide up in the bottom-right corner of the window.

### 1.2 Managing Columns
* **Adding Tickers**: You can repeat the steps above on other cards to add multiple tickers side-by-side.
* **Removing Columns**: Click the small close icon (**`[×]`**) next to the ticker symbol in the column header to remove it.
* **Minimizing**: Click the header or the minimize button (**`—`**) to collapse the widget into a compact header bar without losing your current inputs.

---

## 2. Interactive Input Fields

For each active column, you can edit the following fields to simulate changes:

| Field | Description / Behavior |
| :--- | :--- |
| **Current Share Price** | Defaults to the active price. You can increase or decrease this to simulate price changes. |
| **Simulated Action (Shares)** | Enter positive integers for **Buys** (increases weightage) or negative integers for **Sells / Trims** (decreases weightage). |

---

## 3. Mathematical Reference Engine

Calculations are computed instantly inside your browser without page reloads.

### 3.1 Transacted Amounts & Signs
To make cashflows intuitive:
* **Buys (Outflows)**: Displayed as a negative flow (e.g. `-100.00 USD`) colored **red**.
* **Sells (Inflows)**: Displayed as a positive flow (e.g. `+100.00 USD`) colored **green**.

### 3.2 Dynamic Denominator Weightage Adjustment
When simulating transactions, the total portfolio market value denominator shifts dynamically:
$$\text{Projected Portfolio Weight} = \frac{\text{Current SGD Value} + \text{Transacted SGD}}{\text{Total Portfolio Value} + \sum \text{Transacted SGD}} \times 100$$
This ensures the portfolio allocation projection remains mathematically accurate for capital additions/subtractions.

### 3.3 Position Change Percentage (Trimming/Adding)
To visualize exactly how much you are trimming:
$$\text{Stock Position Change \%} = \frac{\text{Simulated Shares}}{\text{Current Position}} \times 100$$
Trims will display as a negative percentage colored **red** (e.g. `-25.00%`).

---

## 4. Lot Size Guidance Heuristics

Minimum lot sizes are enforced based on asset listings and currencies:
* **Canadian & Singapore Assets** (currency `CAD`/`SGD`, exchanges `TO`/`V`/`SG`, or suffixes `.TO`/`.V`/`.SI`/`.U`): Minimum lot size is **100** shares.
* **US & Others**: Minimum lot size is **1** share.

### 4.1 Lot Size Warnings & Shortcuts
* **Warnings**: If simulated shares are not multiples of the lot size, the input field outlines in yellow with a warning label.
* **Max Populate Link**: Next to the lot size, a clickable `Max: -[qty]` link populates the simulated action box with your entire position size to simulate a full liquidation instantly.
