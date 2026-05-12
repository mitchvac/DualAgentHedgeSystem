# ============================================================
# Dockerfile  —  Dual-Agent Composite Hedge Trading System
# ============================================================

FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create data directory
RUN mkdir -p /app/data/chroma

# Default: paper-trading live mode
ENV PAPER_TRADING=true
ENV LOG_LEVEL=INFO

EXPOSE 8501
EXPOSE 3003

# Entry point — override CMD for backtest, dashboard, or API
CMD ["python", "main.py", "--paper"]
