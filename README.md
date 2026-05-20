# RobeLyrics

Buscador semántico personal del universo Extremoduro / Robe.

Dos modos de búsqueda:

- **Equivalencia metafórica**: traduces una frase de la vida real a una línea del universo Robero (`"se acabó lo bonito"` → `"se acabó la primavera"`).
- **Completar frase**: das el inicio de una línea y devuelve lo que sigue (`"abre, la puerta"` → `"que soy el diablo y vengo con perras"`).

Stack: FastAPI + Next.js + Postgres + Qdrant. Embeddings OpenAI `text-embedding-3-large`, reranker GPT-4o-mini. Knowledge base de fan-content (Reddit, foros, blogs) para que el reranker entienda metáforas no obvias.

> **Uso personal/privado.** Las letras están protegidas por derechos de autor; los ToS de Genius prohíben su redistribución pública. Este proyecto no se sirve a terceros.

---

## Requisitos

- Docker + Docker Compose v2
- Una clave de OpenAI (`OPENAI_API_KEY`)
- Un token de Genius API (`GENIUS_TOKEN`) — gratis en https://genius.com/api-clients
- (Opcional) Credenciales de Reddit y YouTube Data API si vas a ejecutar la Fase 0 completa

## Quickstart

```bash
# 1. Clonar y configurar
cp .env.example .env
# editar .env con OPENAI_API_KEY, GENIUS_TOKEN, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD
# generar JWT_SECRET con: openssl rand -hex 32

# 2. Levantar todo el stack
docker compose up -d --build

# 3. Aplicar migraciones (cuando estén creadas)
docker compose exec api alembic upgrade head

# 4. Verificar que todo está arriba
curl http://localhost:8000/health
# → {"status":"ok","postgres":"ok","qdrant":"ok"}

curl http://localhost:6333/collections
# → {"result":{"collections":[]},"status":"ok"}

open http://localhost:3000
# → placeholder de la web
```

## Servicios y puertos

| Servicio   | Puerto host | Notas                                  |
|------------|-------------|----------------------------------------|
| Postgres   | 5435        | 5432/5433/5434 ya en uso por otros proyectos |
| Qdrant HTTP| 6333        | dashboard en `/dashboard`              |
| Qdrant gRPC| 6334        |                                        |
| API        | 8001        | FastAPI con `--reload`  |
| Web        | 3001        | Next.js dev server      |

## Estructura

```
RobeLyrics/
├── api/           # FastAPI + scripts de ingesta y research
├── web/           # Next.js (App Router)
├── data/          # discography.yaml + sources.yaml
└── docker-compose.yml
```

## Roadmap

1. ✅ Curado de fuentes fan (`data/sources.yaml`)
2. ⏳ **Bloque infraestructura** (esta tanda)
3. ⏳ Fase 0 — Knowledge base de fan-content
4. ⏳ Fase 1 — Ingesta de letras
5. ⏳ API (search híbrido + reranker)
6. ⏳ Frontend (buscador + catálogo)

Plan completo: `~/.claude/plans/quiero-crear-una-p-gina-drifting-koala.md`.
