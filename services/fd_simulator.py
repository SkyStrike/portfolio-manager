import csv
import io
import re
import logging
from collections import defaultdict
from datetime import datetime
from core.database import get_connection

logger = logging.getLogger(__name__)

MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
}

def parse_date_to_month_key(date_str: str) -> str:
    """
    Parses a date string in various formats:
    - m/d/yyyy or d/m/yyyy (e.g., '12/1/2024' or '3/29/2025')
    - yyyy-mm-dd (e.g., '2024-12-01')
    - Month Year (e.g., 'Dec 2024' or 'December 2024')
    Returns a string in YYYY-MM format, or None if parsing fails.
    """
    date_clean = date_str.strip()
    if not date_clean:
        return None

    # Format 1: m/d/yyyy (e.g. 12/1/2024)
    if "/" in date_clean:
        parts = date_clean.split("/")
        if len(parts) == 3:
            if len(parts[2]) == 4:
                try:
                    y = int(parts[2])
                    m = int(parts[0])
                    if 1 <= m <= 12:
                        return f"{y:04d}-{m:02d}"
                except ValueError:
                    pass
            elif len(parts[0]) == 4:
                try:
                    y = int(parts[0])
                    m = int(parts[1])
                    if 1 <= m <= 12:
                        return f"{y:04d}-{m:02d}"
                except ValueError:
                    pass

    # Format 2: yyyy-mm-dd (e.g. 2024-12-01)
    if "-" in date_clean:
        parts = date_clean.split("-")
        if len(parts) >= 2:
            if len(parts[0]) == 4:
                try:
                    y = int(parts[0])
                    m = int(parts[1])
                    if 1 <= m <= 12:
                        return f"{y:04d}-{m:02d}"
                except ValueError:
                    pass

    # Format 3: Month Year (e.g. Dec 2024)
    match = re.search(r'([a-zA-Z]+)\s+(\d{4})', date_clean)
    if match:
        m_str, y_str = match.group(1).lower(), match.group(2)
        m_val = MONTH_MAP.get(m_str)
        if m_val:
            return f"{int(y_str):04d}-{m_val:02d}"

    return None

def parse_fd_rates_csv(csv_content: str):
    """
    Parses CSV content in-memory.
    Format: Date,Institution,Rates
    Example row: Dec 2024,CIMB,2.55% OR 12/1/2024,CIMB,0.0255
    Returns a dict mapping YYYY-MM -> averaged rate float (e.g. 0.0255).
    """
    rates_by_month = defaultdict(list)
    reader = csv.reader(io.StringIO(csv_content))
    
    # Skip header
    try:
        header = next(reader, None)
    except Exception as e:
        logger.error("Error reading CSV header: %s", e)
        return {}

    for row in reader:
        if not row or len(row) < 3:
            continue
        date_str, inst, rate_str = row[0], row[1], row[2]
        
        # Parse date
        month_key = parse_date_to_month_key(date_str)
        if not month_key:
            continue
        
        # Clean rate
        rate_str_clean = rate_str.strip()
        is_pct = False
        if "%" in rate_str_clean:
            is_pct = True
            rate_str_clean = rate_str_clean.replace("%", "").strip()
        
        try:
            rate_float = float(rate_str_clean)
            if is_pct:
                rate_float = rate_float / 100.0
            elif rate_float > 0.1:
                # Value like 2.5 representing 2.5% instead of 0.025
                rate_float = rate_float / 100.0
            rates_by_month[month_key].append(rate_float)
        except ValueError:
            continue

    # Average the rates
    averaged_rates = {}
    for m, r_list in rates_by_month.items():
        if r_list:
            averaged_rates[m] = sum(r_list) / len(r_list)
    return averaged_rates

def shift_month(year_month_str: str) -> str:
    """Shifts a YYYY-MM month string forward by 1 month."""
    y = int(year_month_str[:4])
    m = int(year_month_str[5:7])
    m += 1
    if m > 12:
        m = 1
        y += 1
    return f"{y:04d}-{m:02d}"

def shift_year(year_month_str: str) -> str:
    """Shifts a YYYY-MM month string forward by 1 year (12 months)."""
    y = int(year_month_str[:4])
    m = year_month_str[5:7]
    return f"{y+1}-{m}"

def get_month_range(start_month_str: str, end_month_str: str):
    """Generates an inclusive list of YYYY-MM strings between start and end."""
    months = []
    curr_y = int(start_month_str[:4])
    curr_m = int(start_month_str[5:7])
    end_y = int(end_month_str[:4])
    end_m = int(end_month_str[5:7])
    
    while (curr_y < end_y) or (curr_y == end_y and curr_m <= end_m):
        months.append(f"{curr_y:04d}-{curr_m:02d}")
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1
    return months

def get_monthly_actual_market_values(conn):
    """
    Selects the earliest date with a complete record of the month across active brokers,
    and returns a mapping of YYYY-MM -> liquidation_value.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT date, broker, liquidation_value FROM daily_cash_report ORDER BY date ASC")
    rows = [dict(row) for row in cursor.fetchall()]

    # Retrieve legacy rows if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_cash_report_old'")
    if cursor.fetchone():
        cursor.execute("SELECT date, 'CONSOLIDATED' as broker, liquidation_value FROM daily_cash_report_old ORDER BY date ASC")
        old_rows = [dict(row) for row in cursor.fetchall()]
        dates_in_new = {r['date'] for r in rows}
        for r in old_rows:
            if r['date'] not in dates_in_new:
                rows.append(r)
        rows.sort(key=lambda x: x['date'])

    # Group by month (YYYY-MM)
    rows_by_month = defaultdict(list)
    for r in rows:
        month = r['date'][:7]
        rows_by_month[month].append(r)

    monthly_vals = {}
    for month, m_rows in rows_by_month.items():
        # Get active brokers in this month
        active_brokers = {r['broker'].upper() for r in m_rows}
        # Group rows by date
        by_date = defaultdict(list)
        for r in m_rows:
            by_date[r['date']].append(r)

        # Find the earliest date with complete records
        complete_date = None
        for dt in sorted(by_date.keys()):
            dt_brokers = {r['broker'].upper() for r in by_date[dt]}
            if dt_brokers == active_brokers:
                complete_date = dt
                break

        # Fallback to the earliest date if no complete date is found
        if not complete_date and by_date:
            complete_date = min(by_date.keys())

        if complete_date:
            monthly_vals[month] = sum(r['liquidation_value'] for r in by_date[complete_date])
            
    return monthly_vals

def run_fd_simulation(rate_mode: str, fixed_rate: float, csv_content: str = None):
    """
    Executes the Fixed Deposit comparison simulation.
    """
    conn = get_connection()
    try:
        # 1. Fetch capital injections
        cursor = conn.cursor()
        cursor.execute("SELECT date, amount FROM broker_capital_entries ORDER BY date ASC")
        capital_rows = [dict(row) for row in cursor.fetchall()]
        
        if not capital_rows:
            return {"summary": {}, "rows": []}

        # Sum injections by month (ignore withdrawals, i.e., amount > 0)
        injections_by_month = defaultdict(float)
        for r in capital_rows:
            amt = r['amount']
            if amt > 0:
                injections_by_month[r['date'][:7]] += amt

        # Shift injections by 1 month to set the FD start month
        injections_by_fd_start = defaultdict(float)
        for month, amt in injections_by_month.items():
            injections_by_fd_start[shift_month(month)] += amt

        # 2. Get CSV rates if active
        csv_rates = {}
        if rate_mode == "csv" and csv_content:
            csv_rates = parse_fd_rates_csv(csv_content)

        # 3. Get monthly actual market values
        market_values = get_monthly_actual_market_values(conn)

        # 4. Define simulation ranges
        # Start month is the earliest FD start month
        start_month = min(injections_by_fd_start.keys())
        
        # Current month
        current_date_str = datetime.utcnow().date().isoformat()
        current_month = current_date_str[:7]
        
        # End month is current_month + 12 months
        # Calculate current_month + 12 months (which is exactly shift_year)
        end_month = shift_year(current_month)

        simulation_months = get_month_range(start_month, end_month)

        # 5. Run the simulation month-by-month
        active_fds = [] # list of dicts: {principal, rate, start_month, mature_month}
        total_injected = 0.0
        accum_interest = 0.0
        rows = []
        
        # Determine CSV rate propagation helpers
        last_known_csv_rate = fixed_rate / 100.0

        for M in simulation_months:
            interest_earned_this_month = 0.0
            roll_total = 0.0

            # Step A: Check Maturity
            matured_fds = []
            for fd in active_fds:
                if fd['mature_month'] == M:
                    # Matured!
                    interest = fd['principal'] * fd['rate']
                    interest_earned_this_month += interest
                    roll_total += (fd['principal'] + interest)
                    matured_fds.append(fd)
            
            # Remove matured FDs
            for fd in matured_fds:
                active_fds.remove(fd)

            # Step B: Handle Injections (no injections after current month)
            new_placements = 0.0
            if M <= shift_month(current_month): # injections in current_month are active in shift_month(current_month)
                new_placements = injections_by_fd_start.get(M, 0.0)
                total_injected += new_placements

            # Step C: Get locking rate for month M
            if rate_mode == "fixed":
                current_rate = fixed_rate / 100.0
            else:
                if M in csv_rates:
                    current_rate = csv_rates[M]
                    last_known_csv_rate = current_rate
                else:
                    # Propagate last known rate
                    current_rate = last_known_csv_rate

            # Step D: Roll matured FDs and place new injections
            total_placed = roll_total + new_placements
            if total_placed > 0:
                active_fds.append({
                    "principal": total_placed,
                    "rate": current_rate,
                    "start_month": M,
                    "mature_month": shift_year(M)
                })

            accum_interest += interest_earned_this_month

            # Step E: Valuation metrics
            current_fd_val = sum(fd['principal'] for fd in active_fds)
            
            # Actual market value from DB
            actual_market_val = market_values.get(M)
            
            delta_val = None
            delta_pct = None
            if actual_market_val is not None:
                delta_val = current_fd_val - actual_market_val
                delta_pct = (delta_val / actual_market_val * 100.0) if actual_market_val > 0 else 0.0

            rows.append({
                "date": M,
                "capital_injected": new_placements,
                "total_capital_injected": total_injected,
                "effective_rate": current_rate,
                "interest_earned": interest_earned_this_month,
                "accum_interest": accum_interest,
                "fd_value": current_fd_val,
                "market_value": actual_market_val,
                "delta_val": delta_val,
                "delta_pct": delta_pct
            })

        # 6. Build Summary statistics (for the current month)
        # Find the row corresponding to the current month, or the latest row with a market value
        current_month_row = next((r for r in rows if r['date'] == current_month), None)
        if not current_month_row:
            # Fallback to the latest row with actual market value
            rows_with_market = [r for r in rows if r['market_value'] is not None]
            current_month_row = rows_with_market[-1] if rows_with_market else rows[-1]

        summary = {
            "total_fd_value": current_month_row["fd_value"],
            "total_market_value": current_month_row["market_value"] or 0.0,
            "delta_value": current_month_row["delta_val"] or (current_month_row["fd_value"] - (current_month_row["market_value"] or 0.0)),
            "delta_pct": current_month_row["delta_pct"] or 0.0
        }

        # Format percentage helper
        if current_month_row["market_value"] and current_month_row["market_value"] > 0:
            summary["delta_pct"] = (summary["delta_value"] / current_month_row["market_value"]) * 100.0

        return {
            "summary": summary,
            "rows": rows
        }

    finally:
        conn.close()
