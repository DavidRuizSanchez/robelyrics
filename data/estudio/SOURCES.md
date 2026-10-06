# Estudio del repertorio de Extremoduro y Robe — fuentes y evidencia

Ledger del estudio de Digital PR. **Cada cifra que aparezca en la infografía, el
post o un carrusel tiene que estar aquí**, con su fuente, su filtro y cómo
reproducirla. Si una cifra no está en este documento, no se publica.

- **Extracción:** 06-10-2026
- **Firma:** Entre Interiores · David Ruiz como autor citable
- **Estado:** datos de la ola 1 verificados · pendiente el texto del entregable

## Cómo se reproduce todo

```bash
# 1) páginas públicas de setlist.fm → JSON (1 petición cada 3,5 s)
docker compose exec api python -m scripts.pr.fetch_setlist_index --out /tmp/estudio
# …o, sin red, desde el HTML ya guardado:
#   python -m scripts.pr.fetch_setlist_index --from-raw <dir> --out /tmp/estudio

# 2) dataset propio + cruce (SOLO LECTURA sobre la BD)
docker compose exec api python -m scripts.pr.build_study_dataset \
    --out /tmp/estudio --setlist /tmp/estudio/setlist_stats.json
```

Salidas: `estudio.json`, `repertorio_unificado.csv`, `nunca_tocadas.csv`,
`deuda_setlist.csv`, `versos_mas_repetidos.csv`.

---

## Fuentes

| # | Fuente | Qué aporta | Cómo se consulta | Licencia / condiciones |
|---|---|---|---|---|
| F1 | **BD del proyecto** (`robelyrics`, local) | catálogo, letras, versos, estribillos | SQL de solo lectura | propia |
| F2 | **setlist.fm** | veces que ha sonado cada canción en directo, setlists por año y por gira, toques por disco | 4 páginas públicas de estadísticas | **atribución visible obligatoria y enlace SIN `nofollow`**; uso no comercial; no se republica su tabla |
| F3 | **MusicBrainz** | verificación de tracklists y fechas de disco | API `ws/2`, UA identificada | CC0 |
| F4 | **Search Console** (`data/gsc_page_queries.json`) | demanda de búsqueda real por página | fichero del proyecto | propia |
| F6 | **Consultorio de Juancares** (en corpus) | corroboración de las canciones sin registro en directo | transcripciones de YouTube ya ingestadas | material de un tercero, citado y atribuido |
| F5 | **Wikipedia ES** (`data/reference/wikipedia_giras_facts.md`) | fechas de giras, biografía | fichero del proyecto, extraído 04-06-2026 | CC-BY-SA |

### F2 — manifiesto de descarga (hashes para poder re-verificar)

| URL | SHA-256 (12) |
|---|---|
| `setlist.fm/stats/extremoduro-13d68da1.html` | `30d3c9ead035` |
| `setlist.fm/stats/albums/extremoduro-13d68da1.html` | `884a9928ee01` |
| `setlist.fm/stats/robe-63c74607.html` | `5d9d411aa4ce` |
| `setlist.fm/stats/albums/robe-63c74607.html` | `e6c994022c93` |

**Parseo determinista, no un modelo leyendo la página.** Midiendo lo mismo por
dos caminos salieron cifras DISTINTAS: un resumen de búsqueda daba «Ama, ama,
ama» con 140 toques y «Jesucristo García» con 126, cuando la página dice **143**
y **130**. Las cifras se leen del atributo `data-stats-sort` del HTML, que no
opina (`scripts/pr/setlist_parse.py`).

---

## Registro de cifras

Cada fila es una cifra publicable. `A-nn` es el identificador que usa el
entregable para remitir aquí.

| ID | Cifra | Valor | Fuente | Filtro / periodo | Veredicto |
|---|---|---|---|---|---|
| A-01 | Setlists registrados de Extremoduro | **459** | F2 | 1987-2014, 13 giras | CONFIRMADA |
| A-02 | Setlists registrados de Robe | **132** | F2 | 2017-2024, 6 giras | CONFIRMADA |
| A-03 | Canciones distintas tocadas por Extremoduro | **100** | F2 | — | CONFIRMADA |
| A-04 | Canciones distintas tocadas por Robe | **61** | F2 | — | CONFIRMADA |
| A-05 | Toques totales de Extremoduro | **3.295** | F2 | — | CONFIRMADA (cuadra con su tabla de discos) |
| A-06 | Toques totales de Robe | **2.286** | F2 | — | CONFIRMADA (cuadra con su tabla de discos) |
| A-07 | Filas en `songs` | **153** | F1 | — | CONFIRMADA |
| A-08 | **Composiciones distintas de nuestro catálogo** | **132** | F1 | tras quitar regrabaciones y directos | CONFIRMADA |
| A-09 | **Composiciones sin registro conocido en directo** | **11** de 132 | F1 × F2 | solo discos de estudio y EP | CONFIRMADA (ver registro de afirmaciones) |
| A-10 | Versos en las composiciones canónicas | **6.078** | F1 | solo filas canónicas | CONFIRMADA |
| A-11 | Versos literalmente distintos | **4.237** | F1 | ídem | CONFIRMADA |
| A-12 | **Porcentaje de versos que son repetición** | **30,3 %** | F1 | (6.078−4.237)/6.078 | CONFIRMADA |
| A-13 | Longitud media de un verso | **29,5** caracteres | F1 | — | CONFIRMADA |
| A-14 | Versos repetidos 3+ veces (candidatos a estribillo) | **283** | F1 | `length(text) > 12` | CONFIRMADA |
| A-15 | Descartados por no volver (dispersión < 0,35) | **68** | F1 | — | CONFIRMADA |
| A-16 | **Estribillos identificados** | **215** | F1 | repetición ≥ 3 y dispersión ≥ 0,35 | CONFIRMADA |
| A-17 | **Composiciones con estribillo identificable** | **70** de 132 | F1 | ídem | CONFIRMADA |
| A-18 | Verso más repetido dentro de una sola canción | «De una patada rompo el Sol» y «Luce la oscuridad;», **×12** | F1 | — | CONFIRMADA |
| A-19 | Composición con más versos | **Pedrá, 211** | F1 | — | CONFIRMADA |
| A-20 | **Índice de Resurrección de «Contra todos»** | **×17,7** (2,4 % → 42,4 %) | F2 | 11/459 vs 56/132 | CONFIRMADA |
| A-21 | **Índice de Resurrección de «Si te vas…»** | **×7,7** (7,6 % → 59,1 %) | F2 | 35/459 vs 78/132 | CONFIRMADA |
| A-22 | **Toques de Robe fuera de sus propios discos** | **667 de 2.286 = 29,2 %** | F2 | bloques «Covers» + «Others» | CONFIRMADA |
| A-23 | **Lo mismo en Extremoduro** | **170 de 3.295 = 5,2 %** | F2 | ídem | CONFIRMADA |
| A-24 | Conciertos por año de Extremoduro | 17 años, de 1 (1987) a 53 (1996) | F2 | serie completa: suma 459 | CONFIRMADA |
| A-25 | Conciertos por año de Robe | 2017 (34), 2021 (21), 2022 (41), 2024 (36) | F2 | serie completa: suma 132 | CONFIRMADA |
| A-26 | Disco más tocado por Extremoduro | **Deltoya, 465 toques** | F2 | — | CONFIRMADA |
| A-27 | Densidad de canto máxima | **18,39 versos/min** («Te juzgarán sólo por tus errores») | F1 | tramo primer→último verso; cobertura 109 de 132 | CONFIRMADA |
| A-28 | Densidad de canto mínima | **5,87 versos/min** («Cuarto movimiento: Yo no soy el dueño…») | F1 | ídem | CONFIRMADA |
| A-29 | Demanda de búsqueda cruzada | **89 de 132** composiciones con datos | F4 | 2026-07-10 → 2026-10-02 | CONFIRMADA |
| A-30 | **«Su culo es miel»: la deuda más alta** | 466 impresiones · **1 solo toque en 459 conciertos** | F2 × F4 | ídem | CONFIRMADA |

### Validación cruzada (la prueba de que la extracción está completa)

Dos tablas de **páginas distintas** tienen que dar el mismo total, y lo dan:

| Artista | Suma de la tabla de canciones | Suma de la tabla de discos | ¿Cuadra? |
|---|---|---|---|
| Extremoduro | 3.295 | 3.295 | ✅ |
| Robe | 2.286 | 2.286 | ✅ |

Esto además resuelve una duda: la tabla de canciones de Extremoduro trae
exactamente **100** filas, que es el tope de la página. Si faltaran canciones
—cada una con 1+ toque— las dos sumas no podrían coincidir. **Están todas.**

---

## Registro de afirmaciones

### V-01 · «Hay 11 canciones de estudio sin registro conocido en directo» — CONFIRMADA (ver V-05 sobre cómo se enuncia)

Las 11, cada una verificada como corte real del disco contra **MusicBrainz (F3)**:

| # | Canción | Disco | Año | Verificación en MusicBrainz |
|---|---|---|---|---|
| 1 | Volando Solo | Deltoya | 1992 | ✅ «Volando solo» |
| 2 | Estoy Muy Bien | ¿Dónde están mis amigos? | 1993 | ✅ «Estoy muy bien» |
| 3 | Islero, shirlero o ladrón | ¿Dónde están mis amigos? | 1993 | ✅ «Islero, shirlero o ladrón» |
| 4 | Sin Dios Ni Amo | ¿Dónde están mis amigos? | 1993 | ✅ «Sin dios ni amo» |
| 5 | Adiós Abanico, Que Llego el Aire | Rock Transgresivo | 1994 | ✅ pista 5, «Adiós abanico, que llegó el aire» |
| 6 | Caballero andante | Rock Transgresivo | 1994 | ✅ «Caballero andante (¡¡¡No me dejéis así!!!)» |
| 7 | Érase una Vez | Canciones prohibidas | 1998 | ✅ pista 3, «Érase una vez» |
| 8 | Buitre No Come Alpiste | Yo, minoría absoluta | 2002 | ✅ pista 9 |
| 9 | Cerca del Suelo | Yo, minoría absoluta | 2002 | ✅ pista 7 |
| 10 | Luce la Oscuridad | Yo, minoría absoluta | 2002 | ✅ pista 6 |
| 11 | Manué IV | Para todos los públicos | 2013 | ✅ pista 5 |

**Y además comprobado al revés:** para cada una de las 11 se buscó su mejor
candidato entre los 137 títulos de setlist.fm. El mejor parecido de todas queda
en **≤ 0,58** y apunta a canciones claramente distintas («Sin Dios Ni Amo» →
«Necesito droga y amor», 0,56), así que no son fallos de casado.

### V-05 · La afirmación estaba MAL FORMULADA — CORREGIDA

David objetó que «Cerca del Suelo» no podía no haber sonado nunca, porque la ha
oído. Tenía razón en lo importante: **el dato no soporta «nunca sonó», soporta «no
consta ningún registro»**. Un archivo de conciertos lo rellenan personas; lo que
nadie apuntó no existe en él. El entregable se reformuló entero: titular, texto y
salvedades.

Comprobado al reformular, y es lo que sostiene la lista:

**a) Una segunda búsqueda independiente llegó a 10 de las 11.** El consultorio de
Juancares dedicó dos capítulos a «canciones que no ha llevado nunca Extremoduro al
escenario», sin conocer este estudio:

| Capítulo | URL | Nombra |
|---|---|---|
| 1x04 | `youtube.com/watch?v=fbAKGSeQGy4` | Volando Solo · Sin Dios Ni Amo · Estoy muy bien · Luce la oscuridad · Adiós abanico · Caballero andante |
| 1x05 | `youtube.com/watch?v=ReX6OLBnT90` | Islero shirlero o ladrón · Érase una vez · Cerca del suelo · Buitre no come alpiste |

Solo **«Manué IV»** no aparece en sus listas. Es material de un TERCERO y se cita
como tal: corrobora una ausencia, no es dato propio. Las transcripciones son
automáticas y traen erratas («sex list» por «setlist»), así que se cita la
sustancia, no el literal.

**b) El archivo sí registra lo que sonó una sola vez.** Juancares nombra tres
canciones que sí se tocaron, cada una en una ocasión concreta: «¡Qué sonrisa tan
rara!» y «Tomás» en una prueba en la sala Neptuno de Granada antes de publicar
*Agila*, y «Te juzgarán sólo por tus errores» en la presentación de *Pedrá* (sala
Estudio Rock, Madrid, 1995). **setlist.fm registra exactamente 1 toque de cada
una.** Dos fuentes que no se hablan, coincidiendo en actuaciones únicas de hace
treinta años: es lo que hace informativa la ausencia de las once.

**c) Una prueba en contra, y se publica.** De «Sin Dios Ni Amo», Juancares cuenta
que **un setlist publicado en la revista Heavy Rock** sí la incluía, pero que en las
cintas grabadas en conciertos de esa época no aparece. Es la única de las once con
evidencia a favor y va dicha en el entregable.

**d) «Extraterrestre»**: Juancares apunta que como tal quizá no se tocó nunca y que
se usaba de forma instrumental. setlist.fm le da 43 toques. No se toca el dato; se
anota la discrepancia.

**Consecuencia para el entregable:** el titular pasa de «Lo que nunca sonó» a «Once
canciones sin rastro», el cuerpo dice «no consta» en vez de «nunca», y se añade una
llamada a aportar pruebas — si aparece un registro, la lista se corrige y se dice.

### V-02 · «El verso que Robe repitió 12 veces en una canción que nunca tocó» — CONFIRMADA

«Luce la oscuridad;» aparece **12 veces** en «Luce la Oscuridad» (*Yo, minoría
absoluta*, 2002), con dispersión **0,94** — es el ejemplo de estribillo de
manual que el propio código del proyecto documenta
(`app/services/instagram/momentos.py`). La canción está en la lista V-01.

### V-03 · Casado entre los dos catálogos — CONFIRMADA

121 de los 137 títulos de setlist.fm emparejados con nuestras composiciones. Los
**16 sin casar son correctos**: versiones («Rockin' All Over the World» de
Fogerty, «Juliette» y «Ya no existe la vida» de Platero y Tú, la intro de
Mussorgsky, «Si el cielo está gris» de Extrechinato), un medley («Extremaydura /
J.D. La Central Nuclear»), inéditos («La huella», «La sequía», «Mezclar agua con
sed», «Mi hada», «Te vendería mi alma Lucifer», «Tiempo perdido», «Villancico de
Jesucristo García») y un no-tema («Solo batería»). Ninguno es una composición
nuestra que se nos haya escapado.

### V-04 · Reconciliación de dos composiciones fantasma — APLICADA

`strip_title_suffix` quita todo lo que va entre paréntesis, y en el directo de
1997 el paréntesis lleva **parte del título**:

| Título en la BD | Se absorbe en | Por qué |
|---|---|---|
| «La Pedrá (Fragmento) [En Directo]» | «Pedrá» (*Pedrá*, 1995) | misma composición |
| «Correcaminos (Estate al loro) [En Directo]» | «Correcaminos ¡Estate al loro!» (*Agila*, 1996) | misma composición |

Sin esta reconciliación, las dos salían como «canciones que nunca se tocaron en
directo» — **cuando solo existen tocadas en directo**. La regla aplicada no
adivina nada: un disco en directo o un recopilatorio no estrena composiciones.

---

## Lo que NO se puede afirmar

| Qué | Por qué | Consecuencia |
|---|---|---|
| **Ciudades y recintos** | viven concierto a concierto (46 páginas paginadas) y el WAF corta | fuera de la ola 1 |
| **Primera y última vez que sonó cada canción** | una página por canción, mismo bloqueo | sin «canciones abandonadas» por ahora |
| **Desgloses por gira de setlist.fm** | **no son fiables**: su página de «Agila 96» declara 53 conciertos y su canción más tocada sale con 4 toques; la del setlist promedio avisa de que usó 2 de los 53 | no se usan para series temporales |
| **Giras de Extremoduro: suman 433 de 459** | 26 conciertos no tienen gira asignada en su base | si se publica el reparto por gira, se dice que cubre el 94 % |
| **«71 % de segmentos de concierto identificados»** | cifra interna NO reproducible: no hay script ni salida guardada, y los 3 conciertos transcritos son de 1999, 2012 y 2022, no los «1992, 1997 y 2024» de la documentación | **no se publica** hasta re-medirla |
| **«288 versos repetidos»** | cifra interna obsoleta; hoy son 283 sobre composiciones canónicas | se publica 283 |
| **Autoría de las letras** | `song_credits` tiene 2 filas: está vacía de facto | el pilar de «los poetas» necesita correr `authorship_consensus` primero |
| **Versos por minuto de duración** | `songs.youtube_duration_sec` está vacío en las 153 filas y `duration_sec` solo en 8 | se mide por tramo cantado, que es otra métrica y así se nombra |

### Sesgo que hay que declarar siempre

setlist.fm es un archivo **colaborativo**: 459 setlists no son todos los
conciertos de Extremoduro, son los que alguien subió. La cobertura crece con los
años (1987: 1 concierto registrado; 1996: 53), así que **una canción de los
primeros discos tiene menos toques registrados por el archivo, no
necesariamente porque se tocara menos**. Todo índice comparativo de este estudio
se calcula **normalizado por número de conciertos registrados** de cada
formación, nunca sobre toques brutos.

---

## Refutaciones del análisis de partida

El estudio **no reutiliza** el informe previo generado con Gemini
(`~/Downloads/robe_analisis.html` y su tabla maestra). Sus conteos de setlist.fm
eran correctos, pero la capa que les añadió encima tenía errores en ~8 de las 30
atribuciones comprobadas. Se deja constancia para que no vuelvan a colarse:

| Afirmación de aquel informe | Realidad | Fuente que lo refuta |
|---|---|---|
| Rock Transgresivo es de **1989** | **1994-08-26** | F3 (MusicBrainz) + F1. 1989 es la maqueta |
| «Jesucristo García», «Amor castúo», «Decidí», «Extremaydura», «La hoguera», «Arrebato», «Emparedado», «Romperás» son de Rock Transgresivo | de ***Tú en tu casa, nosotros en la hoguera*** (1990) | F1 y **F2**: setlist.fm las atribuye a ese disco (302 toques) y deja Rock transgresivo en 1 |
| «Por encima del bien y del mal» es de *Lo que aletea…* (2015) | de ***Destrozares…*** (2016) | F1 |
| «Experiencias de un batracio» es de *Canciones 1989-2013* | ese disco no está en el catálogo | F1 |
| Extremoduro tocó **111** canciones distintas | **100** | F2, con la validación cruzada de sumas |
| «Ama, ama, ama» bebe de la poesía de **Marcos Ana** | Marcos Ana alimenta **«Te juzgarán sólo por tus errores (Yo no)»** y «Caballero andante»; «ensancha el alma» apunta a **Manolo Chinato** | corpus (anotaciones de Genius, 12+ fuentes) |
| «Salir» con Robe: 14 % (gráfico) / 17 % (barra) / 24 toques (texto) | **24 de 132 = 18,2 %** | F2 |
| *Tú en tu casa…* (1990) e *Iros todos a tomar por culo* (1997) | **no aparecen en todo el informe** | F1 |

---

## Erratas detectadas de paso (no bloquean el estudio)

1. **`songs.title`**: «Adiós Abanico, Que **Llego** el Aire» — MusicBrainz y la
   edición dicen «que **llegó** el aire». Falta la tilde.
2. **`albums.track_count`**: NULL en los 6 discos revisados, así que no hay
   contraste interno posible contra el nº de filas `songs`.
3. **`songs.youtube_duration_sec`**: 0 de 153 pobladas, pese a que 144 tienen
   `youtube_id`.
4. **`album_tracks`** no cubre *Iros todos a tomar por culo* (1997), que es
   `kind='live'` y tiene filas `songs` propias — de ahí la reconciliación V-04.
