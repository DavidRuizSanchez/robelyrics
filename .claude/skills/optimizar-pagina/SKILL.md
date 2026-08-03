---
name: optimizar-pagina
description: Optimiza UNA página ya publicada de entreinteriores.com cruzando su keyword research (kw_out/) con el contenido real, las queries de GSC y el material disponible en el corpus. Agrupa las keywords por temática, marca cuáles cubre ya el cuerpo y cuáles no, prioriza los huecos por posición real en Google antes que por volumen estimado, y comprueba que exista material verificable ANTES de proponer nada. Entrega un informe con bloques concretos para que un humano apruebe; la escritura la dispara augment_deep, que tiene el contrato de no-pérdida y el gate anti-paja. Usar cuando se quiera mejorar el contenido de un disco, canción, artista o cualquier ficha SEO del proyecto a partir del keyword research ya descargado.
type: workflow
---

# Skill: Optimizar página — del keyword research al contenido

Responde a una pregunta y solo a una: **de todo lo que la gente busca sobre este
asset, ¿qué cubre ya la página y qué no?** Y sobre lo que falta, ¿hay material
real en el corpus para escribirlo, o sería paja?

No es un generador de contenido. Diagnostica, prioriza y propone; escribe
`augment_deep`.

## ⛔ REGLA CRÍTICA — no inventar ni rellenar

- Ningún volumen ni posición se pone «a ojo»: salen de `kw_out/` (DataForSEO +
  Ahrefs, medidos) y de `data/gsc_page_queries.json`. Sin dato → `—`, nunca 0.
- **Un hueco sin material NO se propone.** Antes de sugerir un bloque hay que
  comprobar que el corpus tiene fuentes sobre el asset. Proponer sin material es
  proponer paja, y `augment_deep` lo devolverá como no-op de todas formas.
- Las temáticas excluidas **se listan igualmente** en el informe, marcadas y con
  su motivo. Se ven, no se esconden.

## Cuándo usar este skill

- «optimiza la página de Agila», «qué le falta a esta ficha»
- «aplica el keyword research a los discos / a las canciones»
- «por qué esta página no recibe clics si está en primera página»

## Cuándo NO usarlo

- Generar una ficha desde cero → `scripts.seo.fill_missing_content`.
- Enlazado interno → ya lo hace `autolink_corpus` / `relink_existing`.
- Análisis a nivel de sitio (qué podar, qué fusionar) → skill `site-centroid`.
- Descargar keywords nuevas → `scripts.seo.kw_run` (esto consume las ya
  descargadas; no llama a ninguna API de pago).

## Qué entrega

```
Informe por consola (o --json) con:
  · estado de la ficha       palabras · publicado · target_keyword · meta_title
  · universo de keywords     nº y volumen medido
  · GSC real                 queries, clics y periodo
  · material del corpus      nº de fuentes que mencionan el asset
  · tabla por temática       cubierta / hueco / excluida, con posición real
  · huecos priorizados       con las queries donde Google YA te posiciona
```

## Flujo

### Paso 0 — Comprobar que el corpus está destapado ⚠️ OBLIGATORIO

**Antes de diagnosticar nada.** Si hay fuentes sin indexar, el motor escribe
genérico por mucho keyword research que le des, y regenerar es tirar el dinero.

```bash
docker compose exec -T api python -m scripts.audit_corpus | tail -20
```

Mirar la columna **`NO_SERVIDA`**. Si no es 0:

```bash
# incremental: solo embebe lo que falta, no repaga lo ya indexado
docker compose exec -T api python -m scripts.research.embed_interpretations \
  --only-missing --dry-run     # cuántos chunks faltan
docker compose exec -T api python -m scripts.research.embed_interpretations --only-missing
docker compose exec -T api python -m scripts.audit_corpus | tail -6   # verificar
```

Por qué importa, con números del 03-08-2026: había **355 fuentes no servidas de
695 (51%)** — las 330 transcripciones de YouTube, 16 entrevistas a Robe y 4
biografías **no estaban vectorizadas**, así que ningún retrieval las alcanzaba.
`audit_quality` daba entonces **15 aprobados de 180 páginas**, con el mismo
motivo repetido: *«genérico, no cita versos concretos ni anécdotas trazables»*.
No era el motor: era que no veía la mitad del material.

La causa de que se acumularan: `embed_interpretations` **no era incremental** y
re-embebía las 695 fuentes en cada pasada, así que nadie lo corría. Con
`--only-missing` cuesta unos céntimos y se puede correr siempre.

### Paso 0-bis — Leer las exclusiones
`reference/exclusiones.md`: qué familias se descartan por norma y por qué.

### Paso 1 — Diagnosticar

```bash
docker cp .claude/skills/optimizar-pagina/scripts/diagnose_page.py \
          robelyrics-api:/app/skill_diagnose.py
docker compose exec -T api python /app/skill_diagnose.py --asset album:agila
```

Flags: `--asset tipo:slug` (album | song | artist), `--run <run>` (default: el
más reciente de `kw_out/`), `--incluir compra|merch|descarga`, `--json`.

### Paso 2 — Leer el diagnóstico con criterio

El orden de los huecos **no es por volumen**, es por oportunidad:

1. **Temáticas donde Google ya te posiciona (pos ≤ 20) y la página no habla de
   ellas.** Es el trabajo más barato que existe: ya tienes la posición, solo
   falta el contenido que la justifique.
2. Temáticas sin cubrir con volumen medido.
3. El resto.

⚠️ **Sin umbral de impresiones, a propósito.** `gsc_optimize` exige 20 y por eso
devuelve CERO oportunidades para `/extremoduro/agila`, cuya mejor query
(`agila contraportada`, **posición 8,0**) tiene 6 impresiones. En un sitio de
nicho lo valioso vive por debajo de ese umbral.

### Paso 3 — Comprobar que hay material

El informe da `corpus: N fuentes mencionan «X»`. Si `N == 0`, no se propone
nada: no hay con qué escribirlo. Si hay material, mirar de qué habla antes de
decidir el bloque:

```bash
docker compose exec -T api python -c "
from sqlalchemy import text; from app.db.session import SessionLocal
db=SessionLocal()
for r in db.execute(text(\"SELECT title, url FROM interpretation_sources WHERE content_clean ILIKE :p LIMIT 8\"), {'p':'%Agila%'}): print(r)
"
```

### Paso 4 — Proponer y esperar aprobación

Máximo **2 bloques** por pasada: es el límite real de `augment_deep`. Cada
propuesta lleva la keyword que la justifica, su volumen **medido**, su posición
real y de dónde saldrá el material. **Aquí se para** hasta que el humano aprueba.

### Paso 4-ter — OPTIMIZACIÓN QUIRÚRGICA (la vía que funciona)

Cuando la ficha **ya es buena** (pasó por el motor profundo, tiene metadatos y
fuentes) pero no cubre temáticas con demanda, ni regenerar ni augmentar sirven:
lo probado en Agila es que el motor devuelve no-op o baja el rigor. La vía es
**editar a mano**, con material verificado, y validar con los mismos gates.

Es lo que el encargo pide: reescribir, añadir o reordenar, **sin perder nada**.

**1. Sacar la ficha real de producción** (no la local, que suele estar desfasada):

```bash
# dump a JSON: meta_title, meta_description, target_keyword, body_md
docker compose ... exec -T -e PYTHONPATH=/app api python /tmp/dump_ficha.py
```

**2. Verificar el material ANTES de escribir.** Cada afirmación nueva necesita
fuente en el corpus. Búsqueda por regex sobre `interpretation_sources`:

```sql
SELECT title, url, content_clean FROM interpretation_sources
WHERE content_clean ~* 'agila.{0,60}espabila|portada de .{0,12}agila'
```

Con **menos de dos fuentes independientes, no se escribe**. En Agila hubo tres
para el significado del título y dos para la portada.

**3. Escribir los bloques y ajustar los headings.** Reglas:

- Cada `##` targetea una keyword del research que **encaje de forma natural**.
  «Canciones Clave de 'Agila' y sus Temáticas» → «Las canciones de 'Agila'»,
  porque `extremoduro agila canciones` tiene 720/mes y el otro título no lo
  recogía.
- **El orden se puede cambiar**: en Agila, «qué significa» abre el artículo
  porque es la pregunta más básica y tiene demanda propia.
- **El tracklist NO se escribe en el cuerpo.** La plantilla ya pinta una sección
  «Canciones» con todos los cortes enlazados
  (`web/app/[artist]/[album]/page.tsx`), así que una lista numerada en el
  markdown lo saca **dos veces en pantalla**. Medido el 03-08-2026: se publicó
  así en tres fichas y hubo que corregirlo. Los cortes se citan en prosa cuando
  aportan algo (de dónde viene ese corte, por qué está ahí), nunca como lista.
  La temática «Tracklist y canciones» del diagnóstico ya sale **cubierta** por el
  componente aunque el cuerpo no la mencione.
- `meta_title` ≤ 60 y `meta_description` ≤ 155, con la keyword al principio y
  diciendo lo que la página responde de verdad.
- **Ni un dato del original se cae.** Si condensas redundancia (en Agila, el
  papel de Uoho estaba contado dos veces), los hechos se reubican, no se borran.

**4. Validar con los dos gates antes de tocar nada:**

```python
from app.services.content_guard import no_loss_verdict, find_especulacion
from app.services.editorial_review import review
v = no_loss_verdict(viejo, nuevo)          # 0 pérdidas o no se aplica
find_especulacion(nuevo)                    # tiene que salir vacío
review(viejo, ...).score, review(nuevo, ...).score   # el nuevo no puede bajar
```

⚠️ **`editorial_review` es un LLM y varía entre llamadas** (para el mismo texto
dio 75 y 65). Medir **3 veces cada versión** y comparar medias, no una sola vez.

**5. Aplicar** con `upsert_seo_content(..., force=True)` y `SEO_KEEP_PUBLISHED=1`,
que valida los enlaces internos contra la BD y no tumba la página. Guardar antes
una copia del `body_md` para poder revertir.

**Resultado en Agila (03-08-2026, en producción):** 807 → **926 palabras**,
4 → 6 secciones, 4 → 6 enlaces internos, `title` y `description` reescritos para
las keywords, y las temáticas «significado» (80/mes) y «portada» (100/mes, en
posición 8,0 en Google) pasaron de hueco a cubiertas. Cero pérdidas: mismos
versos, mismos años, mismos temas. Rigor 65 → 65.

### Paso 4-bis — Regenerar el lote viejo

Para las fichas del generador antiguo —sin `outline`, sin `sources_count`, sin
metadatos— el camino no es ampliar sino **regenerar con el motor profundo**, que
es KW-aware y verifica cada sección contra el corpus:

```bash
docker compose exec -T -e SEO_KEEP_PUBLISHED=1 api python -m scripts.seo.regenerate_deep \
  --entity-type album --slugs agila
# el lote entero:  --only-shallow --limit 40
```

`SEO_KEEP_PUBLISHED=1` es obligatorio: sin él la ficha vuelve a borrador y la
página se cae mientras tanto.

**Regenerar es seguro porque hay un gate de no-pérdida** (`content_guard`): si la
versión nueva se deja un verso, un año o un TEMA de los que la ficha ya trataba,
**no se guarda nada** y se informa del motivo. Lo mismo si introduce especulación
que no estaba.

Resultado medido en Agila (03-08-2026): 726 → **914 palabras**, 6 temas
conservados, **cero especulación** (antes repetía «marcó un antes y un después»),
`target_keyword` y `meta_title` rellenos, 36 fuentes del corpus citadas, y la
temática «Portada y arte» —que estaba en posición 8,0 sin mencionarse— pasó a
cubierta.

### Paso 5 — Aplicar (ampliar sin regenerar)

```bash
docker compose exec -T api python -m scripts.seo.augment_all \
  --entity-type album --slugs agila \
  --gap-hint "la portada: quién la ilustró y qué representa"   # opcional
```

Sin `--apply` es dry-run. `augment_deep` compara el rigor antes y después con el
mismo juez (`editorial_review`) y **descarta la ampliación entera si no mejora**.
Un no-op no es un fallo: es el sistema diciendo que no había nada verificable.

**`--gap-hint` existe por un límite real del motor**: su detector de huecos solo
mira 12.000 de los ~70.000 caracteres del dossier, así que un dato que viva más
allá del corte hace que concluya «sin material verificado» teniéndolo delante.
La pista **reordena qué parte del corpus ve**; no añade material ni relaja nada.
Si el corpus no lo respalda, sigue devolviendo no-op.

### Paso 5-bis — LEER lo que ha escrito, antes de publicar

⚠️ **Innegociable.** Medido en Agila el 2026-08-02: con una pista genérica
(«la portada, quién la ilustró») el motor escribió que *«el material no especifica
quién fue el responsable de ilustrar la portada»* —**cuando sí lo especifica**,
con doble fuente: Ramone / Capitán Kavernícola— y rellenó con especulación
(*«puede interpretarse como una metáfora de la libertad»*). El rigor se quedó en
65, igual que antes. **No se publicó.**

El gate anti-paja solo bloquea si el rigor BAJA; un bloque que no mejora nada
pasa. Así que hay que leerlo:

```bash
# imprime la sección nueva sin tocar la BD
docker compose exec -T -e PYTHONPATH=/app api python /tmp/preview.py
```

Se rechaza si: afirma que no hay dato cuando sí lo hay · especula («puede
interpretarse», «podría verse como») · repite lo ya dicho con otras palabras ·
el rigor no sube. En ese caso, el bloque se escribe a mano o se deja el hueco.
**Un hueco es mejor que un párrafo de relleno en una web pública.**

### Paso 6 — Verificar

```bash
docker compose exec -T api python -m scripts.seo.audit_urls   # 0 incoherencias
```

Comprobar además que **no se ha perdido ningún enlace del tracklist** (ver el
aviso de `relink_existing` más abajo).

## El agujero de los metadatos

Medido el 2026-08-02 en la BD local: **159 de 173 fichas publicadas (92%) tienen
`meta_title`, `meta_description` y `target_keyword` vacíos**. Son fichas del
generador viejo, anterior al motor profundo.

Es la optimización más barata del sitio y no necesita contenido nuevo. Si el
diagnóstico marca `⚠️ meta_title VACÍO`, esa página es candidata a
`scripts.seo.optimize_meta` antes que a cualquier otra cosa.

## Reglas que este skill fija

1. **El skill no escribe contenido.** Diagnostica y propone. Escribe `augment_deep`.
2. **Sin umbral de impresiones** al leer GSC.
3. **Máximo 2 bloques** por pasada.
4. **Nada se propone sin material** comprobado en el corpus.
5. **La cola larga no se descarta**: volumen 0 o `—` no es motivo de exclusión.
   Ahí vive el tráfico de letras, significados y acordes.
6. Las temáticas excluidas aparecen en el informe, marcadas.

## Anti-patrones

- **Optimizar para la keyword, no para la temática.** Una página no se optimiza
  para «agila contraportada»: se optimiza escribiendo sobre la portada del disco.
- **Proponer por volumen sin mirar la posición.** 7.000/mes en la posición 40
  vale menos que 100/mes en la posición 8.
- **Escribir el bloque a mano y meterlo en la BD.** Se salta los gates. Todo pasa
  por `augment_deep`.
- **Fiarse de que el hueco existe porque la keyword no está literal en el texto.**
  El detector busca vocabulario de la temática, no la keyword; aun así, leer el
  cuerpo antes de proponer.

## Calibrado del gate de no-pérdida (por si hay que tocarlo)

Todo esto está medido, no supuesto. Si alguien sube un umbral «por si acaso»,
volverá a bloquear regeneraciones buenas:

| Guarda | Valor | Por qué ese |
|---|---|---|
| Versos citados | 0 pérdidas | Bloquea siempre. Es contenido irreemplazable |
| Temas | 0 pérdidas | Léxico primero; si no, coseno contra SECCIONES completas |
| `TOPIC_COSINE_MIN` | **0.45** | Con títulos cortos el coseno es bajísimo: «Contexto histórico y musical» vs «Contexto Histórico y Musical de Agila» da **0.676**, y «Legado» vs «Legado de Agila en la Carrera de Extremoduro», **0.512**. Un 0.72 «razonable» rechazaba todo |
| Enlaces internos | >50%, con suelo de 4 | No bloquean de uno en uno: los reparte `autolink_corpus` con tope 4. Los cortes del propio disco van exentos |
| Años | 0 pérdidas | Los de `[Fuente: … 2021]` NO cuentan: son la fecha de la cita, no un hecho |
| `LENGTH_RATIO_MIN` | **0.70** | Si conserva versos, años y temas, encoger es quitar paja. Con 0.90 bloqueaba condensaciones legítimas |

Y un detalle del pipeline: `editorial_review` devuelve el cuerpo **tensado**
cuando su veredicto es `revise`, y ese tensado puede ser brutal (medido: 6.817 →
2.514 chars). `generate_deep` **descarta el tensado** si deja la ficha por debajo
de lo que ya había publicado. La ficha nueva nunca puede ser más pobre que la vieja.

## Avisos vivos del proyecto

- **`relink_existing` (cron dominical) rota los enlaces del cuerpo.** Deshace los
  enlaces y re-enlaza con `max_links=4`. Que se lleve los cortes del disco **no
  es un bug**: el componente de tracklist los sigue sirviendo (por eso
  `content_guard` los exime y por eso no van en el cuerpo). Lo que **sí** era un
  bug, corregido el 03-08-2026: desnudaba también los enlaces que el autolinker
  no puede reponer —el índice del corpus solo tiene
  album/artist/band/concept/person/place/song/theme—, así que `/sellos/warner` y
  `/libros/de-profundis` se borraban cada domingo para siempre. Ahora solo se
  desnuda lo que está en el índice.
- **Con el tope de 4, una ficha larga no puede lucir todos sus enlaces.** Medido
  en las 5 fichas optimizadas: Agila pasa de 6 a 4 cada domingo y Canciones
  prohibidas cambia cuáles son. Es la regla editorial del Moat, no un fallo; pero
  tenlo en cuenta antes de contar enlaces como logro.
- **Citas a prensa vetada.** Algunas fichas viejas citan Mondo Sonoro o
  Rockdelux, que están en el veto de prensa comercial del proyecto. Si aparecen
  al revisar un cuerpo, señalarlo.
- **`augment_deep` busca por `entity_id`, no por slug.** No pasarle slugs sueltos
  a mano: con homónimos se aumenta la ficha equivocada.

## Dependencias

- Keyword research ya descargado en `api/kw_out/<run>/atribuido/by-owner/`.
  Si falta el CSV del asset, el informe sale con 0 keywords y sigue funcionando
  con GSC y corpus (degrada limpio, no peta).
- `data/gsc_page_queries.json` — lo refresca
  `scripts.seo.gsc_fetch_page_queries --weeks N` (token GSC solo en la Mac).
- BD del proyecto levantada (`docker compose up -d`).
- **Ninguna API de pago.**
