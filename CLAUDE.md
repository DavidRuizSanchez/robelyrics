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
# docker compose exec api python -m scripts.instagram.seed_video_assets  (catálogo de vídeo elegible)
# docker compose exec api python -m scripts.instagram.buscar_conciertos  (cataloga directos de YouTube)
# python -m scripts.instagram.transcribir_concierto --id X   (LOCAL: audio + Whisper)
# docker compose exec api python -m scripts.instagram.propose_clips      (propone clips; NO publica)
# docker compose exec api python -m scripts.instagram.notify_clips       (correo con los clips montados)
# python -m scripts.research.backfill_segments             (tiempos de las transcripciones; LOCAL)
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

## Un post de noticia no se escribe con el titular

El 17-09-2026 salió publicado un post sobre el Día de Extremadura con **fotos de
Pep Guardiola** y afirmando que «figuras del mundo del fútbol como Guardiola
reconocen la influencia de Robe». La noticia iba de **María Guardiola**,
presidenta de la Junta, y el artículo lo decía en su segunda frase. Nadie lo
había leído: el camino de IG no descargaba el artículo.

Las noticias tienen DOS caminos y el de Instagram era un atajo. El del blog pasa
por investigación real y cuatro gates bloqueantes; el de IG pasaba por **una
llamada a gpt-4o-mini** con el titular y 280 caracteres de RSS, a `temperature
0.7`. Ninguna guarda del repo tocaba un caption: ni `editorial_review`, ni
`lyric_guard`, ni `find_especulacion`, ni `web_verify`, ni `image_guard`. Solo
`fact_check` con `use_web=False` dentro de un `try/except: pass`.

Y **se lo ordenaba el motor**, como pasó con los titles SEO: el prompt pedía
«añade SIEMPRE contexto» con cuatro ejemplos musicales, y su cláusula de escape
solo saltaba con «un apellido o nombre común (p.ej. Pérez)». «Guardiola» no le
parece común a un modelo.

**Sin material no hay post.** `article_extract.fetch_article` dice además POR QUÉ
falla, para separar «el medio bloquea bots» (definitivo: la salida es pegar el
texto) de «se cayó la red». `topics._admisible` descarta con motivo y
`publisher.prepare` lanza `SinMaterial`, que cubre el alta manual del panel —
antes un bypass completo. Habrá días de 0 ó 1 noticia: **es lo correcto, no una
avería**.

**El cuerpo del artículo SÍ se persiste** (`news_items.body_*`), cambiando la
política anterior. Vive lo que vive esa tabla (`purge_old`, 7 días): es caché de
trabajo, no archivo, y **no se copia al snapshot de `instagram_queue`**, que es lo
que sobrevive. De un artículo ajeno ahí sigue quedando titular, enlace y extracto.

**El 84,4% de las URLs son de Google News y no redirigen.** `google_news_url`
las traduce con la llamada firmada que usa la propia web. Desde una IP europea
Google manda la primera visita a `consent.google.com` y la página vuelve sin
firma: por eso va la cookie `SOCS`, que es lo que Google deja puesto cuando
alguien responde al banner. **Esto solo se ve en producción**: en un portátil
funciona sin ella. Y destapó un bug viejo — `fetch_article_text` sobre esos
enlaces no «caía al snippet», devolvía el **texto del banner de cookies**, que
pasa de `MIN_CHARS`, así que el `or news.summary` de `scrape_news.py:264` nunca
saltaba y el motor del blog investigaba con la política de privacidad de Google
dentro.

**Quién es quién, antes de escribir** (`news_entities`): las entidades se extraen
del CUERPO, no del titular —«Guardiola» a secas no devuelve ninguna persona en
Wikidata; «María Guardiola» devuelve «política española» a la primera— y se
desambigua contra el **contexto literal de la noticia**, no contra un léxico de
oficios: ni el entrenador ni la presidenta son músicos, y el segundo candidato del
nombre completo es *otra política*, portuguesa. **Con dos candidatos vivos no hay
entidad.** El nombre corto se funde en el completo, o la regla dura silenciaría a
quien el propio artículo identifica.

REGLA DURA: lo que no se identifica no se nombra, no da foto y no da hashtag. Si
es el sujeto, no hay post. Y **se comprueba después, por texto** (`newsroom`), no
se le pide al modelo: es determinista, corre sin clave y es lo que habría parado
el incidente.

**La foto va por procedencia** (`identity_photo`): ficha propia → P18 de Wikidata
del QID resuelto contra Commons → Google con la consulta CONSTRUIDA desde la
entidad → arte propio. `photo_finder` se queda para evergreen y blog. En
`image_guard`, `expected_terms` caza el homónimo de mismo país y distinto oficio
(`_FOREIGN_HINTS` solo veía los de otro país) y es **opt-in**: sin él, el
veredicto es idéntico, porque esa función mueve el cron de las 04:40 y un
`homonym_risk` de más abriría erratas sobre fotos buenas.

En `identity_guard`, **sin foto de referencia se pregunta por CONTRADICCIÓN, no
por reconocimiento**. Un modelo no puede afirmar que una cara es la de una
diputada que no ha visto nunca, y preguntándoselo así dice que sí a todo; sí
puede ver un banquillo y un escudo del City.

**El gate del caption** (`caption_guard`) lo destapó todo: lo falso NO era la
relación —«Guardiola reconoce la influencia de Robe» se sostiene en el artículo,
que habla de un lema inspirado en él— sino el inciso «del mundo del fútbol», un
ATRIBUTO que contradice a la entidad identificada. Eso lo caza
`contradice_la_identidad`, frase a frase (un post de música puede nombrar un
estadio) y buscando también por el apellido: el artículo dice «María Guardiola» y
el caption decía «Guardiola», y sin eso el barrido daba «nada que revisar» justo
del post que había que cazar.

**Las relaciones se comprueban contra el ARTÍCULO, nunca contra la web.** Medido:
`verify_connection('Guardiola','Robe')` devolvía confirmado y su evidencia era la
propia noticia (confirma coaparición, no la relación); y `classify_fact('María
Guardiola es fan de Extremoduro')` volvía `supported` con la evidencia «fan
absoluto que soy de Extremoduro», que es una frase de OTRA persona. La ausencia
de evidencia BLOQUEA — al revés que en `classify_fact`, que existe para no BORRAR
datos de páginas ya publicadas; aquí vamos a AFIRMAR algo nuevo.

**El panel enseña de dónde sale cada cosa** (`instagram_post_evidence`): entidad
resuelta con su descripción y su QID, candidatos descartados, origen y veredicto
de la foto con la consulta literal y su página, y cada afirmación con su
evidencia. Antes decía `imagen ✓` —un booleano— sobre una foto de otra persona, y
la consulta solo quedaba en el log del cron, que rota. Un item `needs_human` **no
se lleva por delante un «aprobar todo»**: cada uno necesita su clic.

`scripts/instagram/audit_identidad.py` barre lo ya publicado. **No borra ni
despublica nada** (no hay camino para ello en el código, y no conviene que lo
haya: retirar un post es manual en instagram.com) y **no va al crontab** hasta
calibrarlo, misma decisión que `audit_published.py`.

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

## Optimizar una ficha no es escribir una nueva

Todas las oportunidades de CUERPO se tiraban para atrás. Reproducidos los rechazos,
**el gate tenía razón**: el motor escribía «La Conexión Filosófica de Interludio» o
«lucha interna, resistencia emocional». Aflojar el listón habría publicado eso.

El fallo estaba antes: **el motor no buscaba lo que la gente pregunta**. No existía
ni una búsqueda por CONSULTA en todo el camino —`gather_entity_dossier` ni siquiera
acepta una— y el corpus tenía guardado lo que respondía de verdad: para «ama ama y
ensancha el alma significado», una anotación de Genius que explica la estrofa y una
entrevista a **Manolillo Chinato**, el autor del poema.

`ModoOptimizacion` (en `augment_deep`) lo construye **solo** `prepare_draft`. La
generación de fichas nuevas no se entera: allí nadie mira antes de publicar.

- **`corpus_for_queries`** busca por la consulta. Umbral 0.45 y dos filtros que el
  parecido no cubre: la prensa vetada seguía indexada (Rockdelux entró a 0.56) y un
  vecino semántico que no menciona nada de lo que se preguntaba no lo responde (un
  corte de Radio Nacional puntuaba más que Chinato). **El material ajeno se cita
  atribuido** — «una anotación de Genius sostiene…» — nunca como voz de Robe.
- **Se dejó de penalizar el crecimiento**, que estaba en el código y no en la
  calidad: el linter contaba repeticiones en absoluto, el juez leía 9.000 caracteres
  y lo añadido va al final (podía puntuar sin haberlo leído, con el aviso del linter
  empeorado por lo que no veía) y la comparación era `<` estricto contra un juez cuya
  varianza está medida aquí. Ahora hay `spotlight`, densidad y tolerancia.
- **La válvula**: lo que el editor jefe rechaza sale igual con el veredicto colgado,
  al correo y al panel, y decide una persona viendo el antes/después. En el correo
  **«publicar todos» NO se las lleva**: cada una necesita su clic, o la válvula sería
  auto-publicación por descuido.

**Abre el juicio sobre si merece leerse, no sobre si es verdad.** Siguen bloqueando
la verificación factual, la no-invención, la no-pérdida y los versos: `lyric_guard`,
que no corría sobre las fichas SEO, corre aquí y cazó un verso inventado en la
primera pasada. Y **mide el DELTA**: su primera versión condenaba a Interludio para
siempre por una cita del libreto ya publicada que no es un verso.

Resultado de la primera tanda real: de 0 borradores a **3 de 6**, y los 3 que no
salen es por no tener material o por citar un verso que no existe.

Ojo con el clasificador: `classify_queries` recibe ahora los **alias** de la BD
(`nombre_alias_index`). Sin ellos, una página que dice «Robe» no cubría «Roberto
Iniesta» y se pedía contenido que ya estaba — 2 de 15 oportunidades, una con 316
impresiones sobre una ficha que tiene la letra entera.

## El title representa la página; la description busca el clic

Criterio de David (22-09-2026), después de rechazar el primer borrador del circuito:

- **El title representa el contenido de la página.** Se optimiza para el término
  principal y, si además se puede hilar otro, bien; **si no se puede, no se fuerza**.
  Nunca se cambia el sentido de un title para colocar una keyword. El borrador que lo
  destapó proponía «Miembros y origen de Barricada: El Drogas y Piedrafita» para una
  página que va del grupo, no de sus miembros.
- **La description no es un elemento de ranking: es lo que capta el clic.** Promete lo
  que se va a encontrar; no resume. «Barricada, grupo musical de Pamplona. Miembros
  clave: … Influencia en bandas como Extremoduro» son tres sintagmas sin un verbo.
- Lo que él escribiría: `Barricada: miembros, historia y legado del grupo de rock
  español` y «Conoce todos los datos de este grupo mítico de rock español y su
  relación con Extremoduro: miembros, historia y legado».

Todo eso vive en **`app/services/seo_style.py`**, que es la ÚNICA fuente: antes había
catorce caminos escribiendo un title con cinco prompts distintos y tres longitudes de
description en circulación (155, 158 y 160), así que cambiar el criterio exigía
acordarse de catorce sitios. Los dos textos de David están congelados como fixture en
`app/tests/test_seo_style.py`: **si alguien toca una guarda y su texto deja de pasar,
la guarda está mal, no el texto.**

La causa raíz no era el modelo: **se lo ordenaba el motor**. En cinco sitios el prompt
pedía la keyword «al INICIO del meta_title», y el `target_keyword` de Barricada es
literalmente `Barricada grupo`. Ahora el término se **cubre**, no se pega: el title de
David cubre `Barricada grupo` entero sin contenerlo.

Cuatro cosas que conviene no deshacer:

- **Ya no se trunca en ningún sitio.** El `[:60]` partía palabras («…amor y libe») y
  es la razón por la que existía `optimize_meta`. Medido: al title de David, de **64
  caracteres**, le quitaba «español». Los topes son dos — `TITLE_TARGET` (60, lo que
  se pide) y `TITLE_HARD_MAX` (65, lo que se rechaza) — y si no cabe limpio se deja
  vacío y lo cubre la plantilla. Su description, de 119, tampoco llegaba al mínimo de
  125 que exigía el prompt: **las constantes contradecían el criterio**.
- **La anti-invención mira cifras y nombres propios, no todas las palabras.** Su
  primera versión tumbó la description de David por «todos», «datos» y «mítico».
- **`letra` NO está en la lista de genéricos vetados.** «Barricada grupo» se veta,
  «Desarraigo letra: …» no: son 99 fichas y es como se busca.
- **Lo que no se puede verificar va al prompt, no a una guarda.** La description
  publicada de Barricada tiene verbos, cabe y cita el diferencial, y aun así es un
  resumen. Eso es un **aviso** que viaja al correo y al panel, nunca un bloqueo.

## Lo que Google dice que falta no siempre es contenido

El correo de los lunes llevaba meses siendo **solo un informe**: listaba URLs en
*striking distance* y remataba pidiendo ejecutar `gsc_optimize --apply` a mano.
Nadie lo ejecutaba, y el `--apply` además regeneraba el cuerpo entero incluso
cuando lo que fallaba era el title. Ese `--apply` está **retirado**.

Lo que decide la acción ya no es la posición, es **medir qué cubre la página**.
Medido el 21-09-2026 contra lo publicado, las tres URLs que el informe ponía
arriba ya tenían el title y la description impecables —la de `interludio` abre su
description con el verso «Dejo las ventanas sin cerrar…» y se lleva 0 clics—: no
les falta contenido, les falta posición. Por consulta con impresiones reales:

| dónde está respondida | acción | consultas | impresiones |
|---|---|---|---|
| en ningún sitio | `body` → `augment_entity --gap-hint` | 131 | 3.087 |
| en el cuerpo, no en la metadata | `meta` → `propose_meta` | 183 | 4.185 |
| en el cuerpo **y** en la metadata | ninguna: es posición | 266 | 12.176 |

El tercer grupo es el más grande y es el único sin acción honesta posible.
**Sale del circuito, pero se cuenta en el correo**: callarlo haría parecer que el
sitio tiene menos margen del que tiene.

`seo_opportunities` sostiene la aprobación en **dos fases** (`detected → approved
→ drafted → applied`): el primer clic autoriza a PREPARAR y el segundo a
PUBLICAR, con un correo de antes/después en medio. Los dos clics viajan en tokens
JWT distintos (`action` dentro del token), así que reenviar el primer correo no
puede publicar nada. La cola se ve en `/biblioteca/admin/seo/oportunidades`.

Tres cosas que conviene no deshacer:

- **La guarda anti-invención de la metadata mira cifras y nombres propios**, no
  todas las palabras. Su primera versión tumbó una description correcta por el
  verbo «cuenta», y una guarda que rechaza lo bueno acaba apagada. Lo que se ha
  inventado aquí alguna vez son datos: un año falso, un homónimo.
- **Una consulta no se compara token a token.** «letras de extremoduro
  desarraigo» en la página que tiene la letra mandaba a escribir lo ya escrito: el
  cuerpo dice «letra», en singular. Hay lista de modificadores de búsqueda
  (`letra`, `wikipedia`, `youtube`…) y cotejo por prefijo de 5 caracteres.
- **Aplicar comprueba que el cuerpo sigue siendo el del borrador.** Entre preparar
  y pulsar pueden pasar días, y aplicar a ciegas pisaría lo que escribiera otro.

Un `noop` es un resultado legítimo y frecuente: si el corpus no respalda nada
nuevo, el gate anti-paja lo tumba (medido: solo 45 de 153 canciones tienen
material para ampliar). Esos también van en el correo, con su motivo.

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

## Las slides no las escribía nadie

`carousel._frases` era un `re.split()` por puntos sobre el resumen que cogía las
tres primeras frases de más de 40 caracteres y les ponía «CLAVE 01» encima. El
carrusel no tenía autor, y de ahí salían «Un Canto a la Libertad» y «La
Evolución Musical de Extremoduro», que están publicados.

Faltaban tres cosas, y ninguna había que inventarla:

- **La voz.** `voice.build_system_prompt` la usan blog, fichas y consultorio;
  Instagram tenía un system prompt propio, defensivo, sin una línea sobre quién
  lee. Ahora hay `family="instagram"`, así que IG hereda las reglas duras del
  sitio (nombre, raya larga, no inventar, no presenciar, 4 líneas de letra). Lo
  que NO se le pasa es `speech_style()`: ese manual es de cómo habla ROBE, y en
  IG Robe no habla — es del consultorio y ahí se queda.
- **El material.** `instagram/material` reúne los pasajes del corpus que
  responden al tema y el dossier de las entidades del catálogo. Devuelve dos
  montones que no son lo mismo: `prompt` (todo, atribuido, para escribir) y
  `verificable` (solo nuestras fichas, para las guardas). Un análisis de un
  tercero es buen material para citarlo y una fuente pésima para dar por buena
  una relación nueva.
- **El juicio de si merece leerse.** `caption_guard` dice si es VERDAD;
  `tono_guard` dice si dice algo. Sus fórmulas son literales medidos en
  producción, y **viajan también al prompt**: que la guarda conozca una lista y
  el prompt no es hacer que el modelo la adivine a base de rechazos.

**El texto nuevo pasa por las guardas.** `newsroom.texto_publicado` incluye las
slides y el cierre. Mientras eran un troceo del caption daba igual —ese texto ya
estaba revisado—, pero en cuanto alguien las escribe son texto nuevo, y texto
nuevo sin gate es por donde entró el post de Guardiola.

Evergreen y blog entran al mismo camino. Su texto de partida sigue intocable (un
verso es de quien lo escribió, y en `quote` la tarjeta lleva el verso: dejar que
el modelo le pusiera título daba «Lágrimas Invisibles» encima de una letra de
Robe). **Sin material no se llama al modelo**: la regla no era «no usar IA», era
«no inventar».

Dos falsos positivos medidos, los dos tumbando noticias legítimas:

- Se le pedía al artículo que demostrara «Robe — versionó a — Extremoduro»,
  porque las dos están siempre en `_entidades_conocidas`. Una relación entre dos
  entidades DE CASA no es una afirmación nueva: es de lo que va la web.
- Un solo reintento para todo. Ahora mentir y sonar a molde se distinguen
  (`Veredicto.estilo`): a un «no escribas "la esencia de Robe"» se le puede
  hacer caso y se da un intento más; el listón de los hechos no se mueve.

Ojo con los topes de las slides: están calibrados contra slides reales, no a
ojo. Con el mínimo en 70 caracteres se descartaba «Pablo Recuero Pérez dirige y
arregla el espectáculo sinfónico» (62), que es justo el dato que se pide.

## Un clip se elige solo, pero no se publica solo

Lo único manual que quedaba era ver el vídeo y teclear `desde` y `hasta`. Todo
lo demás ya estaba: montaje 9:16, veto de canales, atribución quemada, retirada
en un paso y el daemon de la Mac.

**Los tiempos estaban ahí y se tiraban.** Whisper los devuelve con
`verbose_json` y los subtítulos de YouTube traen `start` y `duration`; los dos
caminos aplanaban a texto corrido. Ahora viven en `source_segments`, con el
offset del troceo sumado — sin él, los tiempos del segundo trozo mienten en
veinte minutos. Consecuencia medida: de las 16 entrevistas del corpus, **15 se
recuperaron gratis** desde los subtítulos (`scripts.research.backfill_segments`,
que prueba primero lo gratis y solo paga Whisper con `--whisper`).

**El veto de canal pasa a ser previo** (`video_assets`): antes solo se conocía el
canal real tras descargar, y un preselector así quemaría descargas e intentos.
Sin metadatos no se da por bueno: no saber de qué canal es un vídeo es lo que el
veto tiene que atrapar.

**`clip_picker`** puntúa ventanas de 20-45 s por densidad de habla, menciones del
catálogo, primera persona y limpieza del corte. La frontera se CLASIFICA
(`puntuacion` / `pausa` / `aproximada`) en vez de disfrazarse de exacta: los
subtítulos automáticos llegan sin puntuación, y dar un corte por limpio porque
no se encontró un punto sería justo al revés. Dos cosas que la primera pasada
real destapó: dos de los cinco mejores candidatos eran «bienvenidos al canal», y
se elegían tramos del arranque, que son de quien sube el vídeo.

**El orden importa**: `propose_clips` encola en `proposed` (fuera del goteo), el
daemon lo monta, y SOLO ENTONCES `notify_clips` manda el correo con el vídeo
real. Avisar antes sería pedir que se apruebe una idea. Un botón por clip, nunca
«aprobar todos». Al aprobar entra en la cola por el final y sale con el resto; al
descartar se retira de Cloudinary.

Lo que dice un tramo sirve para ELEGIRLO, no para afirmarlo: el título del post
sale de la procedencia (vídeo y canal), no de resumir la transcripción, que trae
erratas conocidas. Y los medios grandes (Movistar+, RTVE, EL PAÍS, RockFM) no se
vetan —no son discográficas— pero sí se **marcan** en el correo: se reclaman
antes que el clip de un fan, y quien aprueba merece saberlo.

### Cuando un clip no se baja, el orden de diagnóstico

`ffmpeg exited with code 8` ya significa **cuatro cosas distintas**, y el
mensaje no distingue. Los clips llevaban semanas sin poder bajarse (también el
alta manual del panel; no lo rompió la automatización). Medido el 23-09-2026
aislando cada variable:

1. **¿Está yt-dlp al día?** Con 2026.7.4 todas las descargas daban 403, con y
   sin tramo, con node y con deno. Subir a 2026.8.19 lo arregló. YouTube lo
   rompe cada pocas semanas: **mirar esto primero siempre**.
2. **¿Está el challenge solver?** Sin `remote_components: ["ejs:github"]` la
   lista de formatos viene SIN VÍDEO (0 frente a 32 medidos) y se baja solo el
   audio; el montaje muere con un filtergraph que no menciona YouTube.
3. **node ya no vale como runtime**: yt-dlp solo habilita deno, que va en el
   `Dockerfile` de desarrollo (allí corre el daemon).
4. **El códec**: este ffmpeg baja el VP9 y no lo decodifica —ffprobe dice
   «h264» y no entrega un fotograma—, así que se pide H.264 por delante.

Bug propio que escondía los tres primeros: el `outtmpl` fijaba la extensión
(«crudo.mp4»), el audio pisaba al vídeo y el merge se quedaba sin partes.

`_tiene_imagen` intenta DECODIFICAR un fotograma en vez de preguntar a ffprobe
si hay stream, y su error nombra las dos causas conocidas.

## Un clip es un MOMENTO de un concierto

El pipeline de clips (montaje 9:16, veto de canales, atribución quemada,
retirada, daemon de la Mac, un clic por clip) funcionaba, pero apuntaba al
material equivocado: sacaba tramos de entrevistas, y el primero que llegó al
correo era un locutor de radio presentando una canción. Lo que se quiere es un
estribillo con el público cantando, Robe hablando desde el escenario, un solo o
la entrada de un tema, **y que el texto diga de qué momento va y dónde y cuándo
fue**.

**Se midió antes de construir**, porque la memoria del proyecto lo daba por
imposible («las transcripciones de CONCIERTOS están garbleadas») y por eso se
había descartado un setlist matcher. Medido sobre tres conciertos de 1992, 1997
y 2024: **se identifica el 71% de los segmentos con voz** casando contra la
letra de la BD, y en el peor audio (Cáceres 1992) el 80%. Coste: 0,11 $.

Las piezas, y lo que cada una no debe perder:

- **`concierto_meta`** saca fecha y lugar del título y de la descripción (que se
  descargaba y se tiraba). Solo vale lo que consta literalmente, y **el año del
  título manda sobre la descripción**: un vídeo de «sala Vértigo 1993» traía
  «12-09-2016» —cuándo lo subieron— y habría fechado el concierto veintitrés
  años tarde. Sin fecha ni sitio, el post no los menciona.
- **Descarta lo que no son ellos**: tributos (la web está llena: Pedrá, Milongas
  Extremas), ruedas de prensa, reacciones y vídeos de otros grupos. El descarte
  es duro, no una penalización: publicar una banda tributo como si fuera
  Extremoduro es el mismo fallo que confundir a dos personas.
- **`momentos`** clasifica cada tramo. El estribillo no está marcado en ningún
  sitio —Genius los traía y `ingest.py` los borra— pero un verso que se repite
  3+ veces en su canción lo es: 288 versos en 153 canciones. Y `no_speech_prob`,
  que Whisper devolvía y también se tiraba, distingue un solo de un silencio.
- **`clip_picker.candidatos_directo` invierte el criterio** del picker de
  entrevistas, que descarta lo que baja de 7 caracteres por segundo «porque ahí
  hay música»: en un concierto eso es justo el solo.

**REGLA DURA**: la transcripción de un directo sirve para ELEGIR el tramo,
JAMÁS para afirmar lo que se oye. Está garbleada por definición. Lo que el post
afirma sale de la letra de la BD, del catálogo y de los datos del concierto —
por eso el verso que viaja al texto es el de `lines`, no el que transcribió
Whisper, y por eso el kind `live_transcript` no tiene entrada en
`corpus_for_queries._ATRIBUCION`: la guarda que ya existía lo excluye solo de
cualquier cita.

**Quién habla** (`habla_el_protagonista`): en una entrevista, el tramo tiene que
ser del entrevistado. Tres señales gratis —es una pregunta, nombra al sujeto en
tercera persona, usa fórmulas de programa («nos ha dejado», «vamos a escuchar»)—
y un juez barato para lo dudoso. Ante la duda, NO: publicar al locutor es peor
que quedarse sin clip. El tramo que se propuso el 23-09 cae por la primera.

Y un texto corto casa con cualquier cosa: «¡Vamos Manolo!» se identificó como
verso a 0,80 cuando es Robe animando al público. Por eso el listón de parecido
sube cuanto más corto es el fragmento.

### Un estribillo es el que VUELVE, y el clip dura lo que dura

Dos clips rechazados por David el 23-09-2026, con su causa medida:

- **«El estribillo de "Por encima del bien y del mal"» no cantaba el
  estribillo.** Se marcaba como tal cualquier verso repetido 3+ veces sin mirar
  dónde, y en esa canción el más repetido («Todo lo que no está en ti», 4 veces)
  es la LÍNEA 0: sus apariciones caben en las seis primeras de 45. El gancho
  sonaba en 295-302, un segundo después de que el clip acabara. Ahora se mide la
  **dispersión** `(última - primera) / nº de líneas`, umbral 0,35: caen 83 de
  334 versos repetidos. **El criterio NO puede ser la posición**: «Luce la
  oscuridad» también abre su canción y sí es el estribillo (dispersión 0,94).
- **El clip se estiraba hasta 18 s rellenando** con lo que viniera detrás. Ahora
  es el BLOQUE —tramos seguidos del mismo tipo y canción— y dura lo que dure;
  solo se completa por debajo de 10 s y con la misma canción.
- De paso: las dos ventanas candidatas de aquel caso **empataban a 4,00 exacto**
  y ganó la peor por orden de aparición. Se construye un candidato por bloque y
  desempata la cobertura.

Y un vídeo que resultó ser **la portada del disco quieta con el audio encima**.
No se sabe por el título («GIRA 2012 | Robando Perchas en el Hotel»): de 45
conciertos catalogados solo 2 declaran ser audio. Se detecta con
`freezedetect=n=0.003:d=2` sobre el tramo que el daemon ya ha descargado —medido:
100 % congelado frente a 0 % en un directo real— y **no se veta**: puntúa por
debajo y el correo lo enseña marcado, que es lo que pidió David. Mirar el audio
no sirve: el audio SÍ es el del concierto.

Tampoco se propone dos veces la misma canción del mismo concierto: un estribillo
suena varias veces en un bolo y salían dos clips que en el feed se leen igual.

### El rótulo del vídeo no es el título del post

Eran el mismo string (`solicitar` lo usaba para `instagram_queue.title` y para
`video_clips.subtitle`, que es lo que ve `drawtext`), y eso tenía dos
consecuencias: el texto quemado era un titular descriptivo que no engancha, y
**no cabía**. Medido con DejaVu Sans, que es la fuente que resuelve ffmpeg
cuando no se le pasa `fontfile`: «Robe, desde el escenario — La Cubierta,
Leganés, 09-10-1999» ocupa **1622 px** y el hueco útil son **1044** (el lienzo
menos el borde de la caja a cada lado). Como `drawtext` centra, se recortaba
**por los dos lados a la vez**.

Ahora hay campo propio (`video_clips.overlay`) y el rótulo son dos líneas con
jerarquía — dos `drawtext`, no un `\n`, porque un solo filtro las dibuja del
mismo tamaño:

    ¡Menuda locura!                                     ← gancho, ~62 px
    «Por encima del bien y del mal» · Barcelona · 2022  ← dato, ~38 px

Y el tamaño **se ajusta midiendo**: cada línea baja hasta entrar en los 1044 px,
y si ni al mínimo cabe se recorta por palabra, nunca por la mitad de una.

El gancho lo escribe el modelo, pero un rótulo **exclama, no informa**: se le
prohíben las cifras y los nombres propios (el dato va debajo), los emojis
—DejaVu Sans no los tiene y saldría una caja vacía— y las fórmulas de
`tono_guard`. Si falla, una lista de casa elegida por hash del clip, así que el
mismo tramo da siempre el mismo rótulo y re-montar no lo cambia.

En los clips de Robe hablando **no hay gancho**: solo el concierto. La
transcripción de un directo está garbleada y no se cita.

## La pregunta de cierre no es un adorno

Es lo ÚNICO que le pedimos a quien nos lee, y la ponía una plantilla **después**
del gate: `captions.build` añadía el gancho, la pregunta, el verso y el CTA
cuando `caption_guard` y `tono_guard` ya habían dicho que sí. Resultado medido:
**39 de los 309 captions** cerraban con «¿Cómo lo veis vosotros?» o «¿Qué os
parece?», dos fórmulas que el propio linter tenía vetadas.

Ahora la escribe `editorial` con el material delante y viaja en
`newsroom.texto_publicado`, así que la juzgan las mismas guardas que al resto.
Si no sale una que sea de ESTE post, sale vacía.

Tres cosas de criterio, que es donde está la chicha:

- **La frontera no es «pregunta sí o no».** La pregunta funciona — lo que
  sobraba eran las que valen para cualquier post. Las de plantilla ancladas
  («¿Y a ti, qué verso de «Pepe Botika» se te quedó dentro?») se quedan como
  respaldo de lo que no pasa por el redactor: un verso o una efeméride sin
  material no llaman al modelo. Las listas de `news` y `blog` están **vacías a
  propósito**: ahí una plantilla solo podía poner una fórmula.
- **A la pregunta NO se le exige `tiene_ancla`.** «¿Dónde estabas la primera vez
  que escuchaste esto?» no trae ni un año ni un nombre propio, y es de las que
  mejor funcionan. Exigirle un dato se llevaría por delante las buenas.
- **Anclar no basta: hay que variar.** Las dos primeras preguntas reales
  calcaban el ejemplo del prompt con el título cambiado. Eso repetido
  trescientas veces es un molde otra vez, por otro camino, así que al prompt se
  le dice que los ejemplos son la FORMA, no la frase.

`captions_moldes.QUESTIONS` y `tono_guard.PREGUNTAS_DE_MOLDE` viven en ficheros
distintos y podrían divergir —una dice qué se escribe y la otra qué se rechaza—:
un test recorre la primera contra la segunda.

Y una lección que ya va por la tercera vez: **el linter persigue sintagmas, no
palabras**. Vetada «huella imborrable», el modelo escribió «una marca
indeleble»; vetada «la esencia», escribió «su esencia pura». Si se persigue el
sustantivo, basta cambiar el sustantivo.

## Un post preparado no se entera de que has desplegado

`IMAGES_DIR` (`/tmp/robelyrics_instagram`) **no es efímero en producción**: está
montado como volumen docker (`robelyrics_ig-images`) y sobrevive a los
rebuilds. Verificado el 23-09-2026: ficheros de junio vivos en un contenedor
creado ese mismo día.

Por eso `_media_lista` da `True` para todo lo que se preparó alguna vez y
`publish` **no vuelve a llamar a `prepare`**: lo que sale al feed es el texto
que se escribió el día que se preparó el post, con el código de aquel día.
Desplegar una guarda nueva no toca lo que ya está en cola. Para que un item se
reescriba hay que borrarle sus filas de `instagram_queue_media` y vaciar
`caption`/`image_url`/`image_path`.

Antes de rehacer nada en bloque, **datar lo que hay**:
`instagram_queue_media.created_at` dice con qué código se escribió. Ojo al
comparar, que la BD guarda UTC y `git log` muestra hora local.

Y el texto que sale se puede MEDIR sin publicarlo: `tono_guard.moldes_en`
corre sobre el caption guardado, no hace falta adivinar si una cola «lleva las
mejoras». Así se vio que de 25 posts en cola solo uno traía molde.

### El cuentagotas no mira la hora del día

`publish_next` publica cuando pasa el intervalo desde la última vez, así que el
feed acaba con posts a las 02:31 y a las 23:16. Los `IG_SLOTS` (13:30 y 20:30)
**solo gobiernan lo autoprogramado**: quien reparte por horas decentes es
`scheduling.apply_plan`, desde el panel.

Si se programa toda la cola, `next_pending` pasa a devolver `None` y el goteo
deja de mandar: todo sale por `due_pinned` a su hora. Dos cosas que conviene no
olvidar en ese modo — `due_pinned` publica **de una tacada todo lo vencido**
(una caída larga del cron vuelca varios posts juntos al volver), y lo que
encola `prepare_daily` entra SIN fecha, o sea que vuelve al goteo. Conviven.

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
