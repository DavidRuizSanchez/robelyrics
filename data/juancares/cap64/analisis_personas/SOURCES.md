# SOURCES — Personas del cap. 64: criba y propuesta (muestra de 10)

Generado el 10-11-2026 (hora local). Todo es de **producción**, en solo lectura (`ssh robelyrics`): `SELECT` en Postgres y una llamada a DataForSEO desde el contenedor api, que no escribe nada. Lo único que se escribió es local, en esta carpeta.

## Fuentes de datos

| Dato | Fuente | Periodo / filtro | Extracción | Fichero / query |
|---|---|---|---|---|
| Criba de las 77 personas | `entidades_cap64.csv` (informe del 09-11) | tipo = Persona | 10-11 | `scripts/criba_personas.py` → `criba_personas.csv` |
| Menciones en el corpus | prod `interpretation_sources` (sin la 1756), `seo_content`, `posts` | regex sobre `unaccent(lower(texto))` | 10-11 | `scripts/menciones_personas.sql` → `menciones_prod.tsv`; detalle: `scripts/menciones_muestra_detalle.sql` → `menciones_muestra_detalle.tsv` |
| Wikipedia ES | API pública `es.wikipedia.org` | artículo propio de Elia + 9 artículos de contexto | 10-11 17:37 | `scripts/wiki_check.py` → `wiki_check.json` |
| Volumen de búsqueda | DataForSEO `keywords_data/google_ads/search_volume/live` | España (2724), español; 33 keywords | 10-11 16:31 UTC (coste 0,09 USD) | `scripts/volumenes_muestra.py` → `volumenes_muestra.json` |
| Consultas de GSC | volcado `data/gsc_page_queries.json` del commit `b37e8ff` (rama `feat/redes-ga4`) | 14-08 a 06-11-2026 | volcado ya existente | `scripts/gsc_muestra.py` → `gsc_muestra.json` |
| Catálogo y formación | prod `bands`, `albums`, `places`, `persons`, `band_memberships`, `song_credits` | — | 10-11 | `catalogo_relaciones_prod.txt`, `formacion_extremoduro_prod.txt` |
| Forbes España | https://forbes.es/actualidad/647538/el-mural-el-descendimiento-de-plasencia-reconocido-como-el-mejor-mural-del-mundo/ | 11-03-2025 | descargada el 10-11 | cita en A-09 |
| Vozpopuli | https://www.vozpopuli.com/espana/extremadura/plasencia-estrena-un-mural-hiperrealista-de-11-metros-para-promocionar-su-semana-santa.html | 13-02-2025 | descargada el 10-11 | solo da «J.M. Brea» |
| Minutos del vídeo | `../segments.tsv` (fuente 1756) | — | volcado del 09-11; reproducido el 10-11 | `scripts/validar_minutos_muestra.py` → `validacion_minutos_muestra.md` |
| Titles y descriptions | `app.services.seo_style.title_verdict` / `desc_verdict` | contra el esqueleto propuesto | 10-11 | `scripts/propuesta_muestra.py` |

**Volcado de GSC equivocado al principio:** la rama de trabajo (desde `origin/main`) tiene el volcado del 31-07 al 23-10. Se usó el más reciente (14-08 a 06-11), que está en `b37e8ff`. En los dos, ninguna persona de la muestra tiene impresiones por su nombre. Cambian las cifras de «portadas…» (117 en el nuevo), que son las que se citan.

**Lo que NO se ha validado:** GSC sale del volcado del repo y no de la API en vivo, así que va como `no validado contra API`. Las búsquedas web de Susi Iglesias, Paramio y Javi Génesis (sin resultados) son una búsqueda por persona: prueban poco, y por eso no se afirma que «no existan», solo que no se encontraron.

## Validación numérica (10-11-2026)

| Cifra | Dónde | Re-consulta | Resultado |
|---|---|---|---|
| 33 volúmenes de DataForSEO | `personas_propuesta.md` §2, CSV | misma llamada a las 16:36 UTC (`volumenes_muestra_revalidacion.json`) | **0 diferencias** |
| Menciones por candidata (24 filas) | `menciones_prod.tsv` | misma query (`menciones_prod_revalidacion.tsv`) | **idéntico byte a byte** |
| Detalle de las 48 menciones de la muestra | §2 hallazgo 3 | misma query (`menciones_muestra_detalle_revalidacion.tsv`) | **idéntico**: 48 menciones, 40 de Juancares |
| Extractos de Wikipedia | A-04 a A-08 | nueva descarga a las 17:37 (`wiki_check_revalidacion.json`) | **iguales**: QID Q5830178 y los 12 fragmentos |
| Criba: 24 / 23 / 13 / 12 / 5 | §1 | `criba_personas.py` | suman 77 (con `assert` de que no falta ni sobra ninguna) |
| 48 personas de prod, todas con ficha publicada | §5 | query del 10-11 | 48 / 48 |
| 23 minutos citados | `muestra_evidencia.json` | `validar_minutos_muestra.py` | **23 de 23**. La primera pasada falló en 2 (1:02:01 y 2:27:04, minutos del hecho y no del dato), corregidos a 1:02:09 / 1:26:42 y 2:31:49 / 2:32:01 |
| Longitudes de title y description | §3 | `propuesta_muestra.py` | las 12 pasan las guardas |
| 26 relaciones | §4 | recuento de `relaciones_muestra.csv` | 26 |

## Registro de afirmaciones

| ID | Afirmación | Dónde | Evidencia | Veredicto |
|---|---|---|---|---|
| A-01 | La criba deja 24 candidatas (16 de la escena, 8 públicas), 12 con ficha, 13 a la ficha de Robe, 23 de contexto y 5 por identificar | §1 | `criba_personas.csv`, un motivo por fila | CONFIRMADA (criterio propio, aprobado en el plan) |
| A-02 | Las 48 personas de prod tienen ficha publicada | §5 | `select count(*)… from persons` → `48 \| 48 \| 29` (la tercera cifra: 29 sin Wikipedia) | CONFIRMADA |
| A-03 | Una persona sin ficha sale indexable y en el hub | §5 | `web/app/personas/[slug]/page.tsx` y `personas/page.tsx` no contienen `robots` ni `noindex` (grep del 10-11). El hub lista todo `/public/persons` | CONFIRMADA |
| A-04 | Dosis Letal (1983): Luisma Beltrán (guitarra), Juano (voz), Zósimo «Zosi» Pascual (batería) y Paco Doniga (bajo puntual) | §1, §2 | Wikipedia «Extremoduro»: «junto al guitarrista Luisma Beltrán, el vocalista Juano y el baterista Zósimo «Zosi» Pascual —además de la ayuda puntual de Paco Doniga como bajista—». Lo mismo en «Roberto Iniesta» | CONFIRMADA |
| A-05 | (**corregida el 10-11-2026**: la frase de Wikipedia cita como fuente un vídeo de Juancares, nota 25, así que no es corroboración independiente; ver `fuentes_web_personas.md`) Ángel Lorenzo fue el primer batería, unos cuatro meses en 1987, y le sustituyó William | §2 | Wikipedia «Extremoduro»: «el propio Ángel como baterista… y abandonaría la banda unos cuatro meses después». Trembol (corpus 404/472), Robe en 1.ª persona: «un batería, Ángel Lorenzo, … duró solo unos meses y le sustituyó William». Testimonio en 0:54:44 | PARCIAL: su testimonio y la cita de Robe (Trembol); Wikipedia NO es independiente |
| A-06 | Coros: María Timón y Belén en Somos unos animales (3 canciones) y Deltoya (4); Belén también en ¿Dónde están mis amigos?; las dos en Grandes éxitos y fracasos | §2, §4 | Wikipedia, créditos de los cuatro discos (`wiki_check.json`, menciones E-049) | CONFIRMADA |
| A-07 | Elia Blanco: concejala de 1987 a 1991, alcaldesa de 2003 a 2011, condenada por fraude y prevaricación, en prisión en 2015 | §2, §3 | Wikipedia «Elía María Blanco Barbero» (Q5830178), extracto literal en `wiki_check.json` | CONFIRMADA |
| A-08 | José Luis Díaz vetó a Extremoduro y Robe le escribió una carta; dejó la alcaldía en 2003 | §2, §3 | Wikipedia «Extremoduro»: «la banda fue vetada por el alcalde José Luis Díaz… le llevó a escribirle una carta». Mondo Sonoro (corpus 366): «jose luis diaz sanchez … habia dejado de ser alcalde». Wikipedia Elia: «alcalde saliente José Luis Díaz Sánchez» | CONFIRMADA |
| A-09 | (fase 0: la ubicación «en Plasencia» la da nuestra referencia `_ref/robe-solo`, que es la fuente 431 y no prensa ajena; la plaza solo la dice el narrador) Jesús Mateos Brea es un artista placentino, autor de «El Descendimiento» y del macromural de Robe con Manolo Chinato | §2, §3 | Forbes: «realizada por el artista placentino Jesús Mateos Brea». Prensa (corpus 431): «un macromural de jesus mateos brea que une su legado con la poesia de manolo chinato» | CONFIRMADA |
| A-10 | Hay otro mural de Robe en Plasencia, del artista Primo | §2 | **Actualizado en la fase 0**: EFE vía Vivir Ediciones (https://vivirediciones.es/?p=939422, 31-12-2025), descargada el 10-11: «en una de las fachadas de la céntrica plaza de San Martín» | CONFIRMADA |
| A-11 | Mondo Sonoro llama a Paramio «uno de los cofundadores de Extremoduro» | §2 | Corpus 366: «crisna y gabri (los hijos de paramio, uno de los cofundadores de extremoduro)» | CONFIRMADA (la cita). Que sea cierto: sin verificar, contradice la BD |
| A-12 | La coincidencia de Jot Down con Paramio es un falso positivo | §2 | Corpus 382: «escrito por fernando paramio 30/04/2026» (firma de un artículo ajeno) | CONFIRMADA |
| A-13 | La demanda está en los temas: «dosis letal» 170, «dosis letal robe» 70, «mural robe plasencia» 170; ningún nombre pasa de 40 | §2 | `volumenes_muestra.json` (revalidado) | CONFIRMADA |
| A-14 | En GSC ninguna persona de la muestra tiene impresiones por su nombre. Lo único que casa es «dosis letal robe» (2 impresiones, posición 22, en un post) | §2 | `gsc_muestra.json`, periodo 14-08 a 06-11 | CONFIRMADA contra el volcado; no validada contra la API |
| A-15 | En la BD la formación de Extremoduro empieza en Kaíto y William (1987); Ángel Lorenzo no está | §2 | `formacion_extremoduro_prod.txt` (19 filas) | CONFIRMADA |
| A-16 | Ángel, Paco Doniga, Susi Iglesias, Belén y Elia hablan en primera persona en el vídeo | §2, evidencia | Tramos 0:54:44 («me dijo Robert que quería hacer alguna cosilla»), 0:38:48 («podías venir tú, ¿no, Paco?»), 1:58:35 («mi amigo Gustavo y yo éramos compañeros de trabajo»), 1:10:50 («María y yo algunos temas los tocábamos con él»), 1:38:30 («yo tenía una amiga…») | CONFIRMADA |
| A-17 | La entrevista de Disco Cross de 1993 nombra a Belén en los coros | §2 | Corpus 1765: «con coros, eh, Belén. Una de las de todos los discos. María también…». Transcripción automática y no está claro quién habla | PARCIAL: apoya A-06, no se cita |
| A-18 | `song_credits` solo tiene roles de autoría (13 filas) y admite créditos sin persona | §4 | `select credit_role, count(*)` → adaptacion 9, poema_original 2, musica 1, colaboracion 1. El modelo tiene `person_id` nullable y `credited_name` | CONFIRMADA |
| A-19 | Las 12 propuestas de title y description pasan `title_verdict` / `desc_verdict` | §3 | Salida de `propuesta_muestra.py` (`personas_propuesta_muestra.csv`, columnas de veredicto) | CONFIRMADA contra el esqueleto; se repite con el cuerpo real |
| A-20 | Los esfuerzos del §5 | §5 | Sin medir | `[HIPÓTESIS]` |

## Fase 0 (10-11-2026, 17:00-18:10)

| Dato | Fuente | Periodo / filtro | Extracción | Fichero |
|---|---|---|---|---|
| Volúmenes del tema Plasencia (44 keywords) | DataForSEO google_ads search_volume, ES/es, con serie mensual | oct-2025 a sep-2026 | 17:00 UTC (0,09 USD); revalidado a las 17:06, 0 diferencias | `scripts/volumenes_plasencia.py` → `volumenes_plasencia.json` / `_revalidacion.json` |
| GSC del tema | volcado `b37e8ff` | 14-08 a 06-11-2026; regex `plasencia\|mural\|flores amarillas\|dosis letal\|homenaje` | — | consulta en línea (salida en el chat de la sesión); [HIPÓTESIS] conviene guardarla como script |
| Triaje en Wikipedia | API es.wikipedia | 18 búsquedas y 11 artículos de contexto («Plasencia» dio 429, sin leer) | 18:04 | `scripts/wiki_triaje.py` → `wiki_triaje.json` |
| Murales | Vivir Ediciones/EFE, Forbes, Vozpopuli, Street Art Cities, La Ganzúa | — | descargadas el 10-11 | citas en A-10 y A-09 |
| Testimonios | `../segments.tsv` | 14 citas | 10-11 | `scripts/validar_testimonios.py`: 14/14 literales |

| ID | Afirmación | Evidencia | Veredicto |
|---|---|---|---|
| A-21 | «homenaje robe plasencia» tiene de media 2.400, con un pico de 27.100 en dic-2025 y 20-30 al mes desde junio de 2026 | serie mensual en `volumenes_plasencia.json` | CONFIRMADA |
| A-22 | En GSC ninguna página nuestra recibe «robe plasencia» ni los murales; «plasencia extremoduro» tiene 5 impresiones en `/extremoduro` y 4 en `/lugares/plasencia` | volcado de GSC, 14-08 a 06-11 | CONFIRMADA contra el volcado; no validada contra la API |
| A-23 | Ninguna de las 13 candidatas restantes tiene artículo propio en Wikipedia ES | `wiki_triaje.json` → busquedas (la de E-060 dio `cirrussearch-too-busy`: sin comprobar) | PARCIAL: 12 de 13 comprobadas |
| A-24 | Fernando Pizarro (PP) es alcalde desde junio de 2011 | Wikipedia Elía: «En junio de 2011 cedió la alcaldía de Plasencia a Fernando Pizarro, del PP» | CONFIRMADA |
| A-25 | El «Félix» y el «Ventura» de Wikipedia son otras personas (Félix Landa, Félix Arribas, Ventura Rico) | `wiki_triaje.json` → contexto | CONFIRMADA |
| A-26 | Final del Yamaha Band Explosion el 28-09-1989 | Wikipedia «Extremoduro», fragmento en `wiki_triaje.json` | CONFIRMADA |
| A-27 | Ángel Lorenzo nombra al alcalde José Luis Mariño y una reunión con Kaíto y Robe | T-03, 0:57:02-0:57:27, literal | CONFIRMADA (testimonio) |
| A-28 | El «primer disco» de Susi es *Tú en tu casa…* (debut, portada de Rafael Gallego) | `data/reference/rock_transgresivo_y_tu_en_tu_casa.md` (contraportada: «Diseño de portada: Rafael Gallego») + T-10 | CONFIRMADA |
| A-29 | Ya existe `/blog/flores-amarillas-2027-tributo-a-robe-en-plasencia` con impresiones | volcado de GSC: 46 impresiones | CONFIRMADA (que está indexada); no se ha leído su contenido |
