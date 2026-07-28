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
# docker compose exec api python -m scripts.news.aggregate           (27 fuentes → news_items)
# docker compose exec api python -m scripts.instagram.prepare_daily  (selecciona temas y prepara IG)
# docker compose exec api python -m scripts.instagram.publish_next   (publica el siguiente post)
# docker compose exec api python -m scripts.graph.embed_entity_bios  (vectoriza bio_long → entities_v1)
# docker compose exec api python -m scripts.graph.build_graph        (SIEMPRE el ÚLTIMO: reconstruye entity_edges)
```

El **knowledge graph** (`entity_edges`) conecta todas las entidades y alimenta el
motor de contenido (`deep_research.gather_entity_dossier` tira de él para que cada
página cite/relacione/complemente). Es VIVO: `build_graph` es idempotente y un cron
nocturno (03:30 UTC) re-vectoriza + reconstruye el grafo. **Tras cualquier seed o
ingesta que añada entidades/relaciones, correr `python -m scripts.graph.build_graph`.**
Extraer cualquier subgrafo: `scripts.graph.render_subgraph --entity <tipo>/<slug>` o
`GET /admin/graph/<tipo>/<slug>`. Afinidades/datos fuera de corpus se verifican en
Wikipedia/Google (`app/services/web_verify.py`) antes de afirmarse.

Puertos: postgres `5435`, qdrant `6333/6334`, api `8001`, web `3001`.

## Imágenes: ni rotas ni de otro

Dos fallos que volvían una y otra vez, con su causa raíz:

- **Rotas**: las fotos se guardaban como hot-link a `upload.wikimedia.org`, que
  responde **429** cuando el optimizador de Next pide varias desde la IP del server.
  Se rompían unas u otras según el momento. Existía un `--rehost` manual, pero el
  camino de asignación seguía guardando hotlinks: el problema regresaba solo.
- **Falsas**: se buscaban por nombre y se asignaban sin comprobar nada. Se colaron
  tocino ucraniano como «Salo», Fito Páez como Fito Cabrales, un homónimo mexicano y
  una foto de prensa sin fuente como «Rebrote».

`app/services/image_guard.py` es la guarda: **una URL externa nunca llega a la BD**
(`must_rehost` → se re-aloja en Cloudinary antes de guardar) y una foto solo se
publica si su PROCEDENCIA acredita a quién retrata (`verify_provenance` contra las
categorías de Commons, no contra el nombre del fichero). Estados: `accredited`,
`own_art` (arte IA propio: no afirma identidad), `legacy_cc` (re-alojada con autor y
licencia), `unaccredited`, `unverifiable`, `homonym_risk`.

**Ninguna imagen se borra automáticamente.** Los metadatos de Commons son irregulares
(a Leiva lo escriben «Leyva») y un falso positivo borraría contenido bueno de una web
pública. `scripts/seo/audit_images.py --fix --review` (cron 04:40 UTC) re-aloja lo
hotlinkeado y abre errata por cada foto dudosa; el borrado lo ejecuta una persona con
el botón «Arreglar» del panel de erratas.

Al tocar esto, ojo: **`Person` no tiene campo `name`** (es `stage_name` / `full_name`),
y leerlo mal dejaba el nombre vacío marcando como falsas TODAS las fotos de personas.

## Erratas: se arreglan solas o no molestan

El circuito de erratas (`/biblioteca/admin/erratas`) tiene un botón **Arreglar**
(`POST /errata/admin/{id}/fix` → `app/services/errata_fix.py`) que vuelve a pasar el
Motor de Consenso por esa errata concreta con las fuentes de AHORA. Cierra sola lo ya
resuelto, aplica lo que el consenso respalde y, cuando no puede, dice por qué. Mismas
reglas que el barrido: nada se aplica sin corroboración externa.

Caso fuerte: si falta un disco entero (`catalog`), `app/services/catalog_ingest.py` lo
da de alta **de punta a punta** — MusicBrainz (T1) para título/año/tracklist, letras de
LRCLIB/letras.com, embeddings, enlazado de versiones — pero solo si pasa SEIS puertas
duras (score, título, artista, año, tracklist, y que la canción esté en él). Si falla
una, no se toca nada. **Nunca se inventa un tracklist ni una letra.**

Un disco nuevo deja 9 páginas enlazadas que darían 404 hasta tener ficha SEO (cada una
cuesta ~2 min de motor profundo), así que el alta lanza
`scripts.seo.fill_missing_content --album-slug X` desatendido y el cron (04:20 UTC)
repesca lo que falte con `--missing`.

El digest diario (`scripts/notify_review.py`, 09:15 UTC) primero intenta arreglar la
cola y solo después avisa; **solo manda correo si hay novedad** (firma de lo pendiente
en `notification_digests`, recordatorio cada 14 días). `verification_records.applied_at`
distingue lo aplicado de verdad de lo re-verificado: `checked_at` se re-sella cada
noche y por eso el correo repetía siempre las mismas "auto-correcciones".

## Alta manual de noticias: en segundo plano, y con el editor jefe delante

Pegar una URL en `/biblioteca/admin/blog` **no** genera nada en la petición: crea un
`UrlIngestJob` y responde 202 en ~0,2 s. El trabajo lo ejecuta el servidor
(`app/services/url_ingest.py`), así que sobrevive a cerrar la pestaña, y el panel
pregunta por él en `GET /admin/ingest-jobs`. Es obligatorio que sea así: el ciclo
completo mide **264,8 s** en prod y **Cloudflare corta a los 100 s** — en síncrono
solo se veía un `524`, nunca el resultado.

Dos cosas que hay que respetar al tocar esto:

- **Un medio puede bloquear la descarga** (el WAF de deia.eus responde 406 a todo lo
  que no sea un navegador, incluso en su `robots.txt`). No se disfraza el User-Agent:
  el formulario tiene «cuerpo del artículo» para pegar el texto a mano, y con eso el
  resto del pipeline corre igual.
- **El gate de rigor** (`editorial_review`) sí corre aquí, con un reintento de
  investigación reforzada (`research_and_write(boost=True)`) si rechaza. Potenciar es
  traer MÁS MATERIAL REAL, nunca aflojar el listón. Pero el gate es durísimo y falla
  a favor del rechazo, así que «forzar» es la válvula: guarda igual con el veredicto
  colgado. `scripts/blog/audit_published.py` **despublica** lo que el gate rechaza y
  por eso **no está en el crontab**; dejarlo así hasta calibrarlo.

El motor busca el corpus por el sujeto **y** por las entidades citadas
(`news_research.entity_dossiers`): buscar «Bar Umore Ona de Bilbao» daba 0 resultados
mientras «Calle Esperanza S/N» —la canción de la que iba la noticia— daba su letra,
sus créditos y su disco.

El pipeline de noticias e Instagram vive en `app/services/instagram/` y se
gestiona desde `/biblioteca/admin/instagram`. Cron en
`infra/cron/production.crontab`. Guía de migración (jubilación del proyecto
local `entrenoticias/`) en `infra/MIGRATION_ENTRENOTICIAS.md`.

## Decisiones que NO hay que reabrir

- Corpus solo Extremoduro + Robe (no Extrechinato ni Yacumamba).
- Veto a prensa comercial (Mondo Sonoro, Efe Eme, Rockdelux).
- Reddit fuera del corpus (Responsible Builder Policy).
- Embeddings: OpenAI `text-embedding-3-large` (provider abstraído para futuro local).
- Reranker: GPT-4o-mini con structured outputs y citation obligatoria.
- Auth: tabla users + bcrypt directo (passlib falla con bcrypt 5.x).
- Dev workflow: Docker desde día 1, hot-reload con bind mounts.
- Repo personal: `DavidRuizSanchez/robelyrics`.

## Añadir un disco nuevo (cuando Robe publique)

A mano (un disco recién publicado no está aún en MusicBrainz; el alta automática del
consenso solo cubre huecos de catálogo antiguos):

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
