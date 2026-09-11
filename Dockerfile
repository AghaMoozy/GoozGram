# Multi-stage lightweight Python 3.12 production container
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install security updates and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create dedicated non-root user
RUN groupadd -r botgroup && useradd -r -g botgroup -d /app -s /sbin/nologin botuser

# Copy application source code
COPY app/ ./app/
COPY .env.example .

# Create persistent and temporary volume directories
RUN mkdir -p /app/data /app/downloads && \
    chown -R botuser:botgroup /app

USER botuser

# Expose Webhook port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start bot
CMD ["python", "-m", "app.main"]
