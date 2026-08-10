FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.3 /uv /bin/uv
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.12-slim AS runtime

ARG APP_UID=1000
ARG APP_GID=1000

WORKDIR /app

RUN apt-get update && \
    apt-get install --no-install-recommends -y fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid ${APP_GID} ficusacc && \
    useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --shell /usr/sbin/nologin ficusacc && \
    mkdir -p /app/data /app/backups && \
    chown ficusacc:ficusacc /app /app/data /app/backups

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=ficusacc:ficusacc /app/.venv /app/.venv
COPY --chown=ficusacc:ficusacc app/ ./app/
COPY --chown=ficusacc:ficusacc alembic/ ./alembic/
COPY --chown=ficusacc:ficusacc alembic.ini ./

USER ficusacc

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)" || exit 1

# Run the application
CMD ["sh", "-c", "alembic upgrade head && exec waitress-serve --host=0.0.0.0 --port=8000 --threads=4 app.main:app"]
