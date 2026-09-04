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

## El corpus: vectorizar no es servir

`interpretations_v1` tenía el 100% del corpus embebido y aun así **420 de las 731
fuentes eran irrecuperables**. La única lectura de esa colección
(`search_interpretations_for_song_ids`) devuelve `payload.song_ids` para boostear el
ranking, así que una fuente sin canción asociada tenía su hit descartado: 141
transcripciones de YouTube (≈2,6 M de caracteres) y las 110 anotaciones de Genius
—estas además excluidas del ILIKE de `fetch_sources_for_entity`— pagadas en OpenAI y
mudas. El consultorio, encima, no consultaba esa colección en absoluto.

`retrieval.search_interpretations_passages` es el camino que faltaba: recupera por
SIGNIFICADO y devuelve el pasaje. El texto no vive en Qdrant a propósito, pero el
payload guarda `chunk_index`, así que se rehidrata gratis releyendo `content_clean` y
volviendo a trocear con el mismo `chunk_text` del indexado. Lo consumen las fichas SEO
(`deep_research`, bloque 4b), el blog (`news_research.corpus_research`, segunda pasada
tras el ILIKE) y el consultorio.

**En el consultorio ese material entra como material AJENO** (`author_is_robe=False`,
etiquetado «ANÁLISIS DE UN TERCERO») y nunca como voz de Robe. Un análisis de Juancares
o de Tesônica no es algo que Robe dijera, y las transcripciones automáticas traen
erratas (Whisper escribe «Robben y Niesta»): sirven de fondo, no como dato ni cita.

`scripts/audit_corpus.py` (cron 03:30, tras `audit_embeddings`) vigila que esto no
vuelva: cuenta por kind qué fuentes alcanza cada camino y lista las que no alcanza
ninguno. `audit_embeddings` cuenta puntos; este dice si sirven.

## Canales de YouTube: no todos son monotemáticos

Los canales que se barren viven en `data/sources.yaml` con `ingest: true`, y
`detect_uploads` itera todos (antes tenía `juancaraes` hardcodeado). La diferencia está
en `relevance`: `all` se lo traga todo (Juancares, que solo habla de esto) y `catalog`
pasa por `app/services/youtube_relevance.py`, que exige mención de Robe/Extremoduro o
de un título del catálogo — el vocabulario sale de la BD, así que un disco nuevo se
reconoce solo.

@tesonica es el caso: 134 uploads, de los que **39 van del universo Robe** (la serie
completa «LA LEY INNATA — Análisis exhaustivo», armonía y motivos conductores, que no
existe en ninguna otra fuente) y el resto es metal, chelo y vídeos personales.

Dos cosas medidas que conviene no deshacer:

- Los títulos de catálogo **cortos** («Mama», «Golfa», «La Carrera» → «carrera») solo
  casan como palabra completa y **solo en el título**, nunca en la descripción: buscar
  «carrera» en prosa larga metía un vídeo sobre Tarja Turunen que hablaba de «su
  carrera». El umbral está en 10 caracteres porque «La ley innata» normaliza a «ley
  innata», que son exactamente 10.
- El suelo de caracteres de una transcripción **escala con la duración**
  (`min_chars_for`). El valor fijo de 100 agotó los 3 intentos de un tráiler de
  Juancares por «transcripción demasiado corta», y casi la mitad de lo que entra de
  @tesonica son shorts de menos de 90 s.

El motivo del match viaja al email de aprobación: el filtro puede ser generoso porque
la decisión final es tuya, con el CTA de 1 click.

### La cola de ingesta y los rebuilds

Tres cosas que solo se ven cuando el api se reinicia mientras el daemon trabaja (o sea,
en cualquier deploy):

- **Un claim no expiraba.** Si el daemon muere entre `claim` y `complete`, o si recibe un
  502 porque el api está rebuildeando, el vídeo se quedaba en `processing`: `pending` no
  lo listaba y no había reintento posible. Ahora `pending` recoge los `processing` con
  más de `STALE_CLAIM_MINUTES` (30) sin tocar.
- **Un 409 por solape degradaba lo ya hecho.** El launchd dispara cada 15 min; si se
  cruza con una pasada manual, la segunda recibe 409 al reclamar lo que la primera ya
  terminó. Ese 409 se reportaba como fallo y el item quedaba `failed` **con su `done_at`
  sellado**, así que volvía a la cola y se re-pagaba Whisper. Cerrado por los dos lados:
  el daemon reconoce el 409 y `fail` no degrada un `done`.
- **Un 502 masivo no hace daño**, porque el `fail` también falla y no se quema ningún
  intento. Se vio en directo: 31 fallos seguidos durante un rebuild y los 30 vídeos
  siguieron en `approved` con `attempts = 0`.

Los fallos permanentes conviene marcarlos a mano con su motivo en `error` y
`attempts = 3` para que no consuman reintentos en balde. Hay tres así: un directo que
nunca se emitió, un tráiler con 51 caracteres en 36 s (casi sin habla) y una entrevista
de Robe en RockFM con **restricción de edad** — yt-dlp pediría cookies y no se usan; la
salida para esa es pegar el texto en el alta manual del blog.

El pipeline de noticias e Instagram vive en `app/services/instagram/` y se
gestiona desde `/biblioteca/admin/instagram`. Cron en
`infra/cron/production.crontab`. Guía de migración (jubilación del proyecto
local `entrenoticias/`) en `infra/MIGRATION_ENTRENOTICIAS.md`.

## Un post de Instagram que falla no puede evaporarse

Dos fallos que se destaparon juntos cuando el clip de la sala Vértigo, programado
para el 29-jul-2026 a las 20:30, sencillamente no salió:

- **Se re-subía lo que ya estaba subido.** Un clip de terceros lo baja el daemon
  de la Mac y va DIRECTO a Cloudinary: llega con `url` puesta y sin `local_path`,
  sin pisar el `/tmp` del servidor. `_media_lista` lo daba por bueno justamente
  por eso, pero el bucle de subida de `publish()` no hacía la misma comprobación
  y llamaba a `upload_video(None)` → «expected str, bytes or os.PathLike object,
  not NoneType». El comentario del propio bloque ya declaraba la intención
  correcta («si la publicación falla, reintentar no tiene que volver a subir
  nada»); solo faltaba el `if m.url: continue` que la cumpliera.
- **`failed` era terminal de hecho, no por decisión.** `next_pending` y
  `due_pinned` filtran por `pending`/`prepared`, así que un tropiezo transitorio
  borraba el post del calendario para siempre y en silencio. Ahora
  `instagram_queue.attempts` cuenta intentos y ambos selectores repescan lo
  `failed` mientras queden (`config.MAX_PUBLISH_ATTEMPTS`, 3).

Al marcar un fallo, ojo con **de quién es la culpa**: `_marcar_fallo(...,
quema_intento=False)` para lo global (la conexión con Meta caída), porque quemarle
intentos a un post por algo que no es suyo condena a la cola entera. Mismo criterio
que la cola de ingesta de YouTube con los 502 de un rebuild.

El test que existía no cazó nada de esto porque su mock de `upload_video` aceptaba
`None` tan campante: un mock más permisivo que la realidad no prueba el camino que
dice probar.

## Cuando Meta bloquea, la culpa no es del post

El 24-ago-2026 Instagram dejó de publicar y no se supo hasta el 4 de septiembre.
Meta había **restringido la cuenta** (`code 25 / subcode 2207050`, «User access is
restricted»): eso no lo arregla el código, se resuelve entrando a instagram.com
**desde el navegador** y confirmando lo que pida. La causa fue un inicio de
sesión desde una ubicación inusual (el titular, de vacaciones en Pontevedra) —
no el ritmo de publicación ni la API. Ante un 25/2207050, mirar eso primero
(ver `infra/META_RECONNECT.md`).

Lo que sí era nuestro es que un bloqueo reversible se llevara por delante 47 posts:

- **El health check daba verde falso.** `connection_is_healthy()` se apoya en un
  GET, y con la cuenta restringida las LECTURAS siguen funcionando —el IG Graph
  API no expone Account Quality por ningún endpoint—. Verificado en vivo durante
  el incidente: `debug_token` válido, perfil legible, cuota 0/100, vínculo
  Página↔IG intacto. Solo publicar estaba bloqueado. Por eso `puede_publicar` del
  panel NO sale de un GET, sino de los fallos recientes de la cola.
- **Se quemaba intento a ciegas.** `publisher` recibía el error de Meta ya
  serializado a texto por `_create_media`, así que no tenía con qué decidir. Ahora
  `graph_api` devuelve un `MetaError` con `code`/`subcode` y `errors.quema_intento`
  reparte: lo GLOBAL (cuenta, token, cuota, caída de Meta) no gasta intento; lo
  del ITEM (caption largo, aspect ratio, media no descargable) sí. **Un código
  desconocido SÍ gasta**, a propósito: no gastarlo dejaría la cola parada para
  siempre detrás del mismo item —`next_pending` ordena por `position` y reelige
  siempre el primero—, y ese es el fallo silencioso.
- **El cuentagotas dejó de frenar.** El guard de cadencia compara contra
  `_hours_since_last_publish`, que crece sin límite si nada se publica: con todo
  fallando dejaba pasar SIEMPRE, y el cron de cada 15 min intentó 96 veces al día.
  Los 47 posts se condenaron en día y medio, no en once. Cerrado por tres sitios:
  `RETRY_COOLDOWN_H` (6 h) en `_publicable()`, `_pending_count` cuenta también los
  `failed` con intentos, y `due_pinned` ya no gotea encima cuando ninguno salió.
- **No lo vigilaba nadie.** `publish_next` sale con `exit 1` al fallar, pero ese
  código se lo traga el cron y acaba en un log de 8 MB. `scripts.instagram.notify_health`
  (cron 09:20 UTC) avisa por correo. Va aparte del digest de las 09:15 **a
  propósito**: aquel no manda nada si no hay erratas ni posts por revisar, así que
  una caída de IG en semana tranquila habría quedado silenciada otra vez.

El cortacircuitos (`publisher.publicacion_bloqueada`) **no guarda ningún flag**: se
deduce de `last_attempt_at` + `error_code` de la propia cola, así caduca solo y
nadie tiene que acordarse de apagarlo. Abre con un código global conocido, o por
RACHA de `GLOBAL_STREAK` items distintos —esa racha es lo que hace asumible que un
código desconocido gaste intento—. Y no hace falta sondear para saber si se
levantó: al caducar la ventana, el siguiente intento real hace de sondeo. Son 4
intentos al día en vez de 96, y como las URLs de Cloudinary están persistidas,
ninguno vuelve a subir nada.

Para repescar lo condenado: `python -m scripts.instagram.recover_failed --dry-run`.
Devuelve lo evergreen y **descarta la actualidad**, porque una noticia de hace tres
semanas publicada hoy engaña sobre cuándo pasó. Limpia `publish_at`/`publish_on`
vencidos, que no es cosmético: `due_pinned` publica de una tacada todo lo vencido
sin pasar por el cuentagotas, y repescar con las fechas viejas volcaría la cola
entera al feed de golpe. Y va por tandas (`--limit`, 4 por defecto) para no pasar
de `BACKLOG_THRESHOLD` y disparar el modo atasco.

Ojo con dos cosas al tocar esto: el `MetaError` **se pierde en cuanto alguien
escriba `f"...{msg}..."`** en el camino —por eso `post_carousel` reetiqueta con
`_prefijar`, y hay un test que lo vigila—, y `notify_health` no puede fiarse de
`published_at` a secas: si no se publicó nunca es `NULL` y una instalación nueva
se quedaría muda para siempre.

## Un directo no duplica sus canciones

Los discos que **no** son de estudio (`kind` en `live | compilation | single`) no
tienen filas `Song` propias: su tracklist vive en **`album_tracks`** y cada corte
apunta con `song_id` a la grabación **original** de estudio. La relación
canción↔disco es N:M y `songs.album_id` solo modela 1:N; sin esa tabla había que
duplicar la canción, y eso pone en Google dos páginas casi idénticas compitiendo.

Se vio con números al dar de alta los dos «Grandes éxitos y fracasos» (01-08-2026):
33 cortes de los que **29 ya estaban publicados**. Con `album_tracks` los dos
discos suman 2 páginas de álbum y **cero** páginas de canción.

- Poblarlo: `python -m scripts.seed_album_tracks --album-slug X` (tracklist de
  MusicBrainz). Casa por título exacto → alias sin sufijo `(...)` → catálogo del
  otro artista (Robe toca temas de Extremoduro en sus directos, `exact_cross`) →
  aproximado con ratio ≥0.85 **y** longitudes parecidas. El freno de longitud no
  es cosmético: sin él «Extremaydura» casaba dentro de «Villancico del Rey de
  Extremadura». Lo que no casa se guarda **sin enlazar**; nunca se adivina.
- `is_rerecording` se marca comparando el MBID de grabación con el del original.
  Es el dato que acredita que un recopilatorio aporta material y no es relleno de
  sello: 10/15 en el Episodio primero, 14/18 en el segundo, 9/9 en el directo.
- La API manda `path`, `from_album`, `from_year` e `is_rerecording` por corte. El
  frontend **debe** usar `path`: componer la ruta con el álbum actual da 404.
  Va en las dos plantillas, pública y `/biblioteca` (paridad).
- `deep_research._hard_facts` inyecta el tracklist real con su disco de origen.
  Sin eso el motor escribía sobre un disco cuyo contenido no conocía.

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
