import logging
import sqlite3
import os

logger = logging.getLogger(__name__)

DB_FILE = os.getenv("PORTFOLIO_DB_FILE", "data/portfolio.db")

def get_connection():
    """Returns a connection to the SQLite database with foreign keys enabled."""
    if os.path.dirname(DB_FILE):
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    # Return rows as dict-like objects for easier JSON serialization
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Ensures all tables exist (CREATE TABLE IF NOT EXISTS guard) and runs
    runtime data seeding from config JSON files.

    Schema migrations are handled by Alembic (core/migrations.py), which
    runs before this function on startup. This function is kept as a
    belt-and-suspenders guard for fresh databases and to run seeding.
    """
    schema = """
    CREATE TABLE IF NOT EXISTS portfolios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        sort_order INTEGER DEFAULT 0,
        classification TEXT,          -- 'Income + Growth' or 'Discord'
        broker TEXT                   -- 'IBKR' or 'MooMoo'
    );

    CREATE TABLE IF NOT EXISTS tickers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT UNIQUE NOT NULL,
        friendly_name TEXT,
        tax_rate REAL DEFAULT 0.0, -- e.g., 0.15 for 15%
        notes TEXT,
        exchange TEXT,
        underlying TEXT,
        category TEXT
    );

    CREATE TABLE IF NOT EXISTS exchange_rates (
        date TEXT NOT NULL,          -- 'YYYY-MM-DD' or 'latest'
        currency TEXT NOT NULL,
        rate REAL NOT NULL,
        last_updated TEXT,
        PRIMARY KEY (date, currency)
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        portfolio_id INTEGER NOT NULL,
        ticker_id INTEGER NOT NULL,
        date TEXT NOT NULL,          -- Format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD
        action TEXT NOT NULL,        -- 'BUY', 'SELL', or 'SPLIT'
        price REAL NOT NULL,
        quantity REAL NOT NULL,
        currency TEXT NOT NULL,      -- 'USD', 'SGD', 'CAD'
        commission REAL DEFAULT 0.0,
        cost_basis_after REAL,       -- Running cost basis after this transaction
        realized_pl REAL,            -- Profit/loss on SELL transaction
        realized_pl_sgd REAL,        -- Profit/loss on SELL transaction in SGD (based on historical buy and sell rates)
        notes TEXT,
        FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
        FOREIGN KEY(ticker_id) REFERENCES tickers(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS dividends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        portfolio_id INTEGER NOT NULL,
        ticker_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        amount REAL NOT NULL,        -- Gross dividend amount
        currency TEXT NOT NULL,      -- 'USD', 'SGD', 'CAD'
        tax REAL NOT NULL,           -- Calculated or overridden tax paid
        qty REAL,                    -- Quantity of shares at dividend time
        notes TEXT,
        FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
        FOREIGN KEY(ticker_id) REFERENCES tickers(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS ticker_prices (
        ticker_id INTEGER PRIMARY KEY,
        price REAL NOT NULL,          -- Current price (or latest closing price)
        prev_close REAL,              -- Previous day's closing price
        closing_price REAL,           -- Cached closing price
        intraday_price REAL,          -- Cached intraday price
        last_price_mode TEXT,         -- Last price mode used ('intraday' or 'closing')
        currency TEXT NOT NULL,
        last_updated TEXT NOT NULL,
        FOREIGN KEY(ticker_id) REFERENCES tickers(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS upcoming_dividends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker_id INTEGER NOT NULL,
        ex_date TEXT NOT NULL,          -- YYYY-MM-DD
        payment_date TEXT NOT NULL,     -- YYYY-MM-DD
        amount REAL NOT NULL,           -- Gross dividend per share
        currency TEXT NOT NULL,         -- e.g. USD, CAD, SGD
        status TEXT NOT NULL,           -- 'Declared' or 'Estimated'
        last_updated TEXT NOT NULL,
        FOREIGN KEY(ticker_id) REFERENCES tickers(id) ON DELETE CASCADE,
        UNIQUE(ticker_id, ex_date)
    );

    CREATE TABLE IF NOT EXISTS daily_portfolio_metrics (
        date TEXT NOT NULL,
        portfolio_id INTEGER NOT NULL,
        total_invested REAL NOT NULL,
        current_value REAL NOT NULL,
        total_returns REAL NOT NULL,
        PRIMARY KEY (date, portfolio_id),
        FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS daily_options_metrics (
        date TEXT PRIMARY KEY,
        options_profit REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS daily_cash_report (
        date TEXT NOT NULL,
        broker TEXT NOT NULL,
        liquidation_value REAL NOT NULL,
        base_capital REAL NOT NULL,
        total_stock_value REAL NOT NULL,
        cash_on_hand REAL NOT NULL,
        updated_at TEXT,
        PRIMARY KEY (date, broker)
    );

    CREATE TABLE IF NOT EXISTS broker_capital_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        broker TEXT NOT NULL,
        amount REAL NOT NULL,
        remarks TEXT,
        UNIQUE(date, broker, amount, remarks)
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ticker_price_history (
        symbol   TEXT NOT NULL,
        date     TEXT NOT NULL,   -- YYYY-MM-DD
        interval TEXT NOT NULL,   -- '1d' or '1wk'
        open     REAL,
        high     REAL,
        low      REAL,
        close    REAL NOT NULL,
        PRIMARY KEY (symbol, date, interval)
    );
    """
    conn = get_connection()
    try:
        with conn:
            conn.executescript(schema)

        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error("Error initializing database: %s", e)
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
