"""
core/logging_config.py

Central logging configuration for the portfolio-manager application.

Call configure_logging() inside the FastAPI startup_event (after uvicorn
has applied --log-config via dictConfig). This is necessary because uvicorn
resets the root logger handlers when it is imported, wiping any handlers
installed at module-load time.

All modules use:

    import logging
    logger = logging.getLogger(__name__)

and inherit the format/level from the root logger configured here.
"""
import logging
import os
import sys

LOG_FORMAT = "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """
    Install or re-install the root logger handler with the standard format.

    This should be called from the FastAPI startup_event, after uvicorn has
    applied --log-config. Calling it earlier (at module import) is ineffective
    because uvicorn.config calls logging.config.dictConfig() which replaces
    root handlers.

    Level is controlled by the LOG_LEVEL environment variable (default INFO).
    Third-party libraries that are overly verbose are suppressed to WARNING.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing StreamHandler to avoid duplicate lines, then add ours
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)

    # Replace existing handlers so we don't double-print
    root.handlers = [handler]

    # Suppress noisy third-party loggers
    for noisy in ("yfinance", "urllib3", "httpx", "peewee", "hpack", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Re-enable all loggers that might have been disabled by dictConfig
    for name, log in logging.Logger.manager.loggerDict.items():
        if isinstance(log, logging.Logger):
            log.disabled = False

