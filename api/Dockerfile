# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base

# uv viene como binario estático; lo copiamos desde la imagen oficial
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Dependencias de sistema mínimas (psycopg binary trae libpq, pero gcc ayuda
# si alguna lib pide build at install time)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalación de dependencias en una capa cacheable
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev || \
    uv sync --no-install-project --no-dev

# El código se monta como bind-mount en docker-compose para hot-reload,
# pero en build incluimos lo que haya por si se ejecuta sin volumen.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
