# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies needed for python-multipart and compiling certain packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python packages
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    yfinance \
    python-multipart \
    pandas \
    requests \
    python-dotenv \
    jinja2 \
    pytz \
    alembic \
    sqlalchemy

# Copy the application code into the container
COPY . /app

RUN find /app/patching -type f -name "*.sh" -exec chmod +x {} +

# Create directory for persistent sqlite and cache volume mounting
RUN mkdir -p /app/data

# Expose port 8080
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORTFOLIO_DB_FILE=/app/data/portfolio.db
ENV exchange_rates_file=/app/data/exchange_rates.json
ENV exchange_rates_max_poll_hours=6
ENV exchange_rates_decimals=4
ENV BASE_PATH=""
ENV LOG_LEVEL=INFO

# Run the FastAPI server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--log-config", "log_config.json"]

