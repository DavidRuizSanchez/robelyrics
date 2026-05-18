# RobeLyrics — Guía rápida para futuros agentes

Buscador semántico personal del universo **Extremoduro** y **Robe**. Stack: FastAPI + Postgres + Qdrant + Next.js 15. Uso privado con auth.

## Estética del frontend ("Entre Interiores")

- **Paleta**: granate `#a83a3a` sobre fondo deep-black `#0d0b0a`. Texto `#ede4d3` (papel). Acentos con divisores `rgba(237,228,211,0.08)`.
- **Tipografía**: serif **Cormorant Garamond** para titulares y letras (cuerpo grande, itálica para versos), mono **JetBrains Mono** para etiquetas y badges (10-13px, letterspacing 2-4px, uppercase), hand **Caveat** ornamental.
- **Tono**: editorial nocturno, minimalista, "guiños sin copiar marcas" — el logo "Sol & Nube" y el delfín ornamental son referencias al tatuaje de Robe pero no calcan ninguna marca registrada.
- **Cursor**: InkCursor granate personalizado en desktop (`pointer: fine`); el cursor real se oculta vía `cursor: none` global. El InkCursor se agranda al pasar sobre links/botones (`[data-cursor=hover]`).

## Estructura del repo

```
api/        FastAPI + scripts (ingesta, research, embeddings, distill, match_*)
web/        Next.js 15 (App Router) + Tailwind
data/       discography.yaml + sources.yaml (semilla)
docker-compose.yml (4 servicios)
```

## Cómo arrancar

```bash
cp .env.example .env  # rellenar OPENAI_API_KEY, GENIUS_TOKEN, JWT_SECRET, ADMIN_*, YOUTUBE_API_KEY
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m scripts.seed_admin
docker compose exec api python -m scripts.seed_catalog
# Para repoblar todo:
# docker compose exec api python -m scripts.ingest          (letras desde Genius)
# docker compose exec api python -m scripts.embed_lyrics    (vectoriza líneas+chunks)
# docker compose exec api python -m scripts.research.fetch_*  (fan content)
# docker compose exec api python -m scripts.research.link_sources_to_songs
# docker compose exec api python -m scripts.research.distill --only-missing
# docker compose exec api python -m scripts.research.vectorize_consensus
# docker compose exec api python -m scripts.research.update_interpretations_payload
# docker compose exec api python -m scripts.match_youtube
# docker compose exec api python -m scripts.match_lrclib
```

Puertos: postgres `5435`, qdrant `6333/6334`, api `8001`, web `3001`.

## Decisiones que NO hay que reabrir

- Corpus solo Extremoduro + Robe (no Extrechinato ni Yacumamba).
- Veto a prensa comercial (Mondo Sonoro, Efe Eme, Rockdelux).
- Reddit fuera del corpus (Responsible Builder Policy).
- Embeddings: OpenAI `text-embedding-3-large` (provider abstraído para futuro local).
- Reranker: GPT-4o-mini con structured outputs y citation obligatoria.
- Auth: tabla users + bcrypt directo (passlib falla con bcrypt 5.x).
- Dev workflow: Docker desde día 1, hot-reload con bind mounts.
- Repo personal: `DavidRuizSanchez/robelyrics` (NO la organización Convertix).

## Añadir un disco nuevo (cuando Robe publique)

1. Editar `data/discography.yaml` con `slug`, `title`, `year`, `kind: studio`.
2. `python -m scripts.seed_catalog` (idempotente, añade el album).
3. `python -m scripts.ingest --album-slug <slug>` (descarga letras).
4. `python -m scripts.embed_lyrics` (re-vectoriza incrementalmente).
5. `python -m scripts.match_youtube` y `python -m scripts.match_lrclib`.
6. Tras un fetch nuevo de fan-content: link_sources → distill --only-missing → vectorize_consensus → update_interpretations_payload.

## Referencias

- Plan maestro: `~/.claude/plans/quiero-crear-una-p-gina-drifting-koala.md`.
- Memoria del proyecto: `~/.claude/projects/-Users-david-ruiz/memory/project_robelyrics.md`.
- Pitfalls técnicos: `~/.claude/projects/-Users-david-ruiz/memory/project_robelyrics_gotchas.md`.
