FROM python:3.14-slim

# Install uv (fast Python package manager) and system cron daemon
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && \
    apt-get install -y --no-install-recommends cron && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer — only rebuilds when lock file changes)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy source code
COPY . .

# Collect static files (no-op today since assets are CDN-only)
RUN uv run python manage.py collectstatic --noinput

# Persistent data directory (overridden by DATA_DIR env var → Docker volume)
RUN mkdir -p /app/data

RUN chmod +x /app/deploy/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
