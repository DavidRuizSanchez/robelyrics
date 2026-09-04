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
# `nodejs` es para yt-dlp, no para el proyecto: YouTube firma las URLs de vídeo
# con un desafío que hay que resolver ejecutando JavaScript, y sin intérprete la
# descarga acaba en 403 — que con ffmpeg de por medio se reporta como «exited
# with code 8» y no dice nada de la causa. Pasó el 03-08-2026 con un clip que se
# quedó en «FALLIDO» en el panel. El daemon de clips corre DENTRO de este
# contenedor (infra/local/clips_daemon.sh), así que el intérprete tiene que
# estar aquí, no en la Mac.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ffmpeg \
        fonts-dejavu-core \
        nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalación de dependencias en una capa cacheable.
#
# CON las de desarrollo (pytest, ruff), a diferencia de `Dockerfile.prod`, que
# sigue con `--no-dev`. Esta imagen es donde se corren los tests: el proyecto no
# tiene CI, así que `docker compose exec api pytest` es la única red que hay. Y
# estaba puesta con alfileres: la imagen traía pytest de una capa antigua, no
# porque el Dockerfile lo instalara, así que el primer rebuild que invalidara la
# caché dejaba el proyecto sin forma de correr los tests. Pasó el 03-08-2026 al
# añadir nodejs.
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project || \
    uv sync --no-install-project

# El código se monta como bind-mount en docker-compose para hot-reload,
# pero en build incluimos lo que haya por si se ejecuta sin volumen.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
