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
| A-20 | **Índice de Resurrección de «Contra todos»** | **×4,1** (10,3 % → 42,4 %) | F2 | 11/107 (2008-14) vs 56/132 | CORREGIDA en V-06 |
| A-21 | **Índice de Resurrección de «Si te vas…»** | **×1,8** (32,7 % → 59,1 %) | F2 | 35/107 (2008-14) vs 78/132 | CORREGIDA en V-06 |
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

### V-09 · El verificador de autoría NO es reproducible: no se relanza (07-10-2026)

Tras arreglar la consulta (V-07) relancé `authorship_consensus` tres veces más. El
arreglo funcionó —rescató «Última Generación», y el caso Chinato subió a 0,93 con
corroboración de Google y de la voz de Robe—, pero al repetirlo apareció algo peor
que el defecto original: **el mismo claim recibe veredictos distintos en pasadas
consecutivas.**

| Afirmación | Pasada 2 | Pasada 3 | Pasada 4 |
|---|---|---|---|
| «Te juzgarán sólo por tus errores» → Marcos Ana | 0,67 retenida | **0,80 APLICADA** | **0,50 retenida** |
| «Puta» → Federico García Lorca | **0,80 APLICADA** | 0,67 retenida | 0,67 retenida |
| «Buscando una Luna» → Antonio Machado | 0,74 | 0,87 | **0,59** |

La confianza de una misma afirmación oscila entre **0,50 y 0,87** según los
fragmentos que devuelva el buscador en ese momento y cómo los lea el juez. No es una
medición: es un sorteo con sesgo favorable.

**Consecuencia que hay que conocer: `apply_credits` es ADITIVO.** Comprueba si el
crédito ya existe y, si no, lo inserta; nunca retira. Así que relanzar acumula lo que
cualquier pasada haya aprobado. Estado actual: **14 créditos en 13 canciones de 12
autores**, de los cuales **dos quedaron aplicados en una pasada y retenidos en la
siguiente** («Puta» → Lorca y «Te juzgarán» → Marcos Ana).

**Qué se hace con esos dos: se quedan.** Los dos tuvieron corroboración externa en la
pasada que los aplicó, y los dos están documentados **con los versos citados** en el
artículo de Jot Down; para Lorca existen además dos piezas publicadas tituladas «Lorca
en la Música Popular (IV): Extremoduro – *Puta*». Retirar dato cierto porque una
búsqueda flojeó es el error que este proyecto ya tiene anotado en
`gotcha_guards_falsos_positivos`: guardas que protegen el fallo en vez del dato.

**Qué NO se hace: relanzar.** Cada pasada reparte distinto y acumula. Si hay que
rehacer la autoría, se vacía `song_credits` primero y se corre UNA vez.

**Y qué se publica en el estudio.** La autoridad citable no es el veredicto del motor,
es **el artículo de Jot Down (2017)**, que es una pieza publicada y firmada que cita
los versos de cada préstamo. El estudio cita eso, y señala aparte las que tienen
además corroboración independiente estable: Chinato en «Ama, ama, ama» (0,93 con
Google y voz de Robe), Neruda en «Sucede», Ramón Romero Ruiz en «Todos me dicen».

**Las cuatro que no ha corroborado nunca ninguna pasada** —Shakespeare y Zorrilla en
«Hoy te la meto hasta las orejas», Miguel Hernández en «Prometeo», Marcos Ana en
«Caballero andante» y **Santos Isidro Seseña en «Salir» y «Standby»**— van al estudio
como `[HIPÓTESIS]` citando Jot Down, nunca como dato. Y lo de Santos Isidro Seseña
sigue siendo informativo por sí mismo: cero fuentes externas en cuatro intentos encaja
con la duda de un comentarista del propio artículo, que sospecha que es un seudónimo
de Robe.

### V-08 · Geografía: 591 conciertos extraídos, y tres saneados que hacían falta (07-10-2026)

`crawl_setlist_browser --what conciertos` recorrió el índice entero: **46 páginas de
Extremoduro y 14 de Robe**, 1 petición cada 3,5 s. Resultado: **591 conciertos, los 591
con fecha, 568 con ciudad** — y 459 + 132 cuadra exactamente con los totales que
declara setlist.fm, así que la extracción está completa.

| Cifra | Valor |
|---|---|
| Conciertos documentados | **591** (459 Extremoduro + 132 Robe) |
| Con fecha | 591 |
| Con ciudad | 568 (23 sin ella: entradas donde solo consta el festival) |
| Ciudades distintas | **193** |
| Ciudades con un solo concierto | **106** |
| En España | **559** |
| Fuera de España | **9** — Argentina 4, Uruguay 2, Colombia 1, Ecuador 1, Chile 1 |
| Top ciudades | Madrid 34 · Barcelona 19 · Cáceres 15 · Zaragoza 15 · Valladolid 13 · Sevilla 12 · A Coruña 12 · Valencia 12 · Granada 11 · Bilbao 11 · **Plasencia 11** |
| Top recintos | Sala Zeleste 8 · Coliseum da Coruña 7 · Recinto Hípico (Cáceres) 7 · Sala Canciller 6 |

**Tres saneados, los tres necesarios, con su medición:**

1. **Exónimos ingleses.** setlist.fm escribe algunas ciudades españolas en inglés:
   «Seville» tenía **12** conciertos y convivía con «Sevilla» como si fueran dos
   sitios. También «Cordova». Mapeados.
2. **`Unknown Venue` encabezaba el ranking de recintos con 31.** Es el literal que usa
   setlist.fm cuando no se sabe dónde fue; no es un recinto. Excluido.
3. **Los nombres genéricos de recinto contaban categorías, no sitios.** «Plaza de
   Toros» sumaba **16** conciertos de dieciséis plazas distintas, y «Campo de Futbol»
   (6) y «Campo de fútbol» (6) iban por separado por la tilde. Ahora los genéricos se
   cualifican con su ciudad —«Recinto Hípico (Cáceres)»— y si no hay ciudad, se caen.

También se corrigió un falso positivo propio: «Casal de Festes» es una sala y la
detección de festivales la clasificaba como festival por la subcadena «fest». Ahora
van tokens completos.

**Dos lecturas que cambian el relato de partida:**

- **Toda la aventura americana son nueve conciertos.** El informe previo hablaba de
  «expansión latinoamericana» y de «primera gira por Hispanoamérica» como fenómeno; en
  el registro son 9 noches de 591.
- **Extremadura pesa más que Barcelona.** Cáceres (15) y Plasencia (11) suman **26**
  frente a los 19 de Barcelona. Plasencia, donde Robe nació y fundó el grupo en 1987,
  tiene tantos conciertos registrados como Bilbao o Granada.
- Y las dos etapas reparten distinto: Extremoduro concentraba (Madrid 29, Barcelona 14,
  Cáceres 12) y Robe esparce (Valencia 6 es su máximo, Madrid baja a 5).

### V-07 · Autoría: 10 atribuciones aplicadas, 7 retenidas (07-10-2026)

Se escribieron 17 hipótesis en `data/song_credits.yaml` leyendo a mano el artículo
**«Extremoduro y la literatura» (Jot Down, 2017)**, que documenta más de veinte
préstamos citando los versos, y se pasaron por
`scripts.verify.authorship_consensus --pending --apply`.

**Aplicadas (10, con corroboración externa):**

| Canción | Autor | Rol | Confianza |
|---|---|---|---|
| Ama, Ama, Ama y Ensancha el Alma | Manolo Chinato (+ Robe, música) | poema_original | 0,92 |
| Sucede | Pablo Neruda | adaptacion | 0,88 |
| Pedrá | Manolillo Chinato | adaptacion | 0,87 |
| Ábreme el Pecho y Registra | Sor Kampana | adaptacion | 0,86 |
| Todos Me Dicen | Ramón Romero Ruiz | poema_original | 0,86 |
| Deltoya | Kiko Luna Creciente | adaptacion | 0,83 |
| Posado en un Nenúfar | Raúl Lomas | adaptacion | 0,83 |
| Quemando Tus Recuerdos | Manolillo Chinato | adaptacion | 0,83 |
| Malos Pensamientos | Sor Kampana | adaptacion | 0,80 |
| Buscando una Luna | Antonio Machado | adaptacion | 0,74 |

**Retenidas para revisión humana (7, confianza 0,67 y cero corroboración externa):**
«Te juzgarán sólo por tus errores» y «Caballero andante» (Marcos Ana), «Prometeo»
(Miguel Hernández), «Salir» y «Standby» (Santos Isidro Seseña), «Hoy Te La Meto Hasta
Las Orejas» (Shakespeare) y «Puta» (Lorca).

**OJO: retenidas NO es refutadas.** Tres observaciones sobre por qué cayeron:

1. **La consulta web que construye el motor es una frase que nadie escribe**:
   `«En la canción «Puta», Federico García Lorca firma la parte de adaptacion»`
   (`authorship_consensus._web_source`). Para Lorca sí existe corroboración —los
   propios comentarios del artículo enlazan dos piezas tituladas «Lorca en la Música
   Popular (IV): Extremoduro – *Puta*»—, pero esa búsqueda no la encuentra. Una
   consulta del tipo `"Puta" Extremoduro Lorca poema` la traería.
2. **El motor etiqueta la hipótesis como `fan_feedback`** sea cual sea su `source`, así
   que no pondera que venga de un artículo de revista publicado y firmado.
3. Las retenidas son precisamente las de **autor célebre**: buscar «Lorca» o
   «Shakespeare» junto a una canción devuelve ruido sobre el autor, no la atribución.
   Las que pasaron son las de autores específicos del entorno (Sor Kampana, Raúl Lomas,
   Ramón Romero Ruiz), donde la búsqueda sí aterriza en el documento concreto.

**Hallazgo lateral que sí cuenta como dato:** de **«Santos Isidro Seseña» no apareció
ni una fuente externa** en ninguna de sus dos canciones. Coincide con la duda que
levanta un comentarista del propio artículo de Jot Down —que el poeta no exista y sea
un seudónimo de Robe— y es una línea que merece perseguirse por sí misma.

**Dos límites del verificador, medidos:**
- Comprueba **un solo crédito por canción** (el primero con rol `poema_original`,
  `letra` o `adaptacion`) y, si pasa, escribe TODOS los de esa entrada. Machado y
  Chinato en «Caballero andante» y Zorrilla en «Hoy Te La Meto» no se evaluaron
  (tampoco se escribieron: su crédito principal quedó retenido).
- **«Última Generación» se saltó en silencio**: su único crédito es `colaboracion`, rol
  que no está en esa lista. Sigue en el YAML sin procesar.

### V-06 · Los índices estaban MAL NORMALIZADOS — CORREGIDOS (crawl con navegador, 06-10-2026)

Dos errores míos, encadenados, y el segundo invertía una conclusión del estudio.

**a) «Los desgloses por gira de setlist.fm no son fiables» era FALSO.** Lo medí con
`httpx` y leí el HTML **sin hidratar**: la página de «Agila 96» parecía declarar 53
conciertos con un máximo de 4 toques. Con un navegador real esperando a
`tr.songRow`, el año 2008 pasa de 0 a **1.011 toques en 47 conciertos**. No era su
dato, era mi medición. La serie por año de Extremoduro suma **3.295**, exactamente su
total, y la de Robe **2.286**, exactamente el suyo: ambas completas y validadas.

**b) La mayoría de las fichas antiguas NO LISTAN el repertorio.** Medido:

| Época | Setlists | Toques | Toques por setlist |
|---|---|---|---|
| 1987-2002 | 315 | 708 | **2,2** |
| 2004 | 37 | 151 | 4,1 |
| 2008-2014 | 107 | 2.436 | **22,8** |

El **78,5 % de las interpretaciones registradas sale de 2008-2014**, que es el 23 % de
los conciertos. Así que dividir los toques por los 459 setlists —lo que hacía el
`indice_resurreccion` de la primera versión— **hinchaba los porcentajes de Robe hasta
tres veces**, porque Robe tiene 132 setlists todos con repertorio y Extremoduro 459 de
los que solo ~107 lo traen.

**Qué cambia:** la comparación se hace entre épocas de densidad equivalente —
Extremoduro 2008-2014 (107 conciertos) frente a todo Robe (132) — y **el relato se
invierte**:

| Canción | Antes (÷459) | Corregido | %E 08-14 | %R |
|---|---|---|---|---|
| Contra todos | ×17,7 | **×4,1** | 10,3 % | 42,4 % |
| Si te vas… | ×7,7 | **×1,8** | 32,7 % | 59,1 % |
| Ama, ama, ama | ×2,3 | **×0,7** | 96,3 % | 71,2 % |
| Dulce introducción al caos | ×2,0 | **×0,5** | 96,3 % | 43,9 % |
| La vereda de la puerta de atrás | ×1,5 | **×0,4** | 81,3 % | 31,8 % |

De las **24** canciones que tocaron las dos formaciones, solo **2 suenan más con
Robe** y **22 menos**. La «resurrección del repertorio» no existe como fenómeno
general: existe en «Contra todos» y en «Si te vas…», y nada más.

Y aparece el hallazgo que lo sustituye, más fuerte porque es contraintuitivo: **el
Extremoduro final tenía un repertorio casi inmóvil** —«Standby» en el 98,1 % de sus
conciertos, «Puta» y «Salir» en el 97,2 %, «Dulce introducción al caos» y «Ama» en el
96,3 %, «Rockin' All Over the World» en el 86,9 %— mientras que **a Robe no hay nada
que le pase del 72 %**. El informe de partida afirmaba justo lo contrario («la
monolitización del directo» de Robe, «una curaduría de rigidez asombrosa»).

**Páginas que no cargaron y cómo se cerraron:** 1997 y 1999 se recuperaron al
reintentar (39 y 72 toques). **1987 tiene cero de verdad**: su único setlist no lista
repertorio. Dos giras («Robando perchas del hotel», «Somos unos animales») siguen sin
recuperar, pero no hacen falta: la serie por AÑO ya cuadra con el total.

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
| ~~Ciudades y recintos~~ | **resuelto**: índice recorrido entero, 591 conciertos (V-08) | publicable |
| **Primera y última vez que sonó cada canción** | una página por canción, mismo bloqueo | sin «canciones abandonadas» por ahora |
| ~~Desgloses por gira no fiables~~ | **Era mi medición, no su dato** — ver V-06. Con navegador son correctos y la serie por año cuadra con el total | se usan, leídos con navegador |
| **Densidad desigual por época** | las fichas de 1987-2002 traen 2,2 canciones por concierto y las de 2008-2014, 22,8 | toda comparación va entre épocas equivalentes, nunca sobre los 459 |
| **Giras de Extremoduro: suman 433 de 459** | 26 conciertos no tienen gira asignada en su base | si se publica el reparto por gira, se dice que cubre el 94 % |
| **«71 % de segmentos de concierto identificados»** | cifra interna NO reproducible: no hay script ni salida guardada, y los 3 conciertos transcritos son de 1999, 2012 y 2022, no los «1992, 1997 y 2024» de la documentación | **no se publica** hasta re-medirla |
| **«288 versos repetidos»** | cifra interna obsoleta; hoy son 283 sobre composiciones canónicas | se publica 283 |
| **Autoría de las letras** | 11 créditos aplicados con corroboración (V-07); 7 atribuciones retenidas sin verificar | el pilar de «los poetas» se publica con las 10 confirmadas; las 7 van como `[HIPÓTESIS]` o fuera |
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

---

## Validación de cierre de la sección `/estudios` · 07-10-2026

La infografía se publica como página del sitio
(`/estudios/repertorio-en-directo-extremoduro-robe`). **Ninguna cifra ha cambiado**
respecto a la versión ya validada arriba: el texto es el mismo, y lo único que se ha
tocado es (a) el sello del pie, que decía «Borrador del 6 de octubre de 2026, no
publicado», (b) el aviso «boceto · datos verificados» de la cabecera, los dos
retirados al publicar, y (c) el tooltip del mapa, que ahora dice «y N más» cuando una
provincia tiene más ciudades de las tres que lista.

Cifras citadas en `SEO_ASSETS.md` que salen de este estudio, re-verificadas contra
`web/components/estudio/datos-repertorio.ts`, que es el fichero que rinde la página:

| Cifra afirmada | Dónde se afirma | Fuente re-consultada | Valor devuelto | Veredicto |
|---|---|---|---|---|
| Versiones en Extremoduro: 170 (5,2 %) | SEO_ASSETS.md A-2 | `DISCO_E` | 170 · 5.2 | CUADRA |
| Versiones en Robe: 667 (29,2 %) | SEO_ASSETS.md A-2 | `DISCO_R` | 667 · 29.2 | CUADRA |
| Cáceres, 37 conciertos | SEO_ASSETS.md A-1 | `PROV["Cáceres"].n` | 37 | CUADRA |
| Barcelona, 33 conciertos | SEO_ASSETS.md A-1 | `PROV["Barcelona"].n` | 33 | CUADRA |
| Madrid, 48 (la única por encima) | infografía, sección del mapa | `PROV["Madrid"].n` | 48 | CUADRA |
| Plasencia, 11 conciertos | SEO_ASSETS.md A-1 | `PROV["Cáceres"].ciudades` | 11 | CUADRA |

Cifras nuevas de `SEO_ASSETS.md`, con su fuente y su comprobación:

| Cifra | Fuente | Filtro | Comprobado | Veredicto |
|---|---|---|---|---|
| 39 términos consultados, 13 a 0 búsquedas | Ahrefs Keywords Explorer | país `es` | 07-10-2026 | CUADRA |
| `robe plasencia` 200/mes · `letras de extremoduro` 150 · `extremoduro caceres` 30 · `versiones de extremoduro` 10 | Ahrefs | país `es` | 07-10-2026 | CUADRA |
| 26 posts publicados | `posts` en producción | `status='published'` | 07-10-2026 | CUADRA |
| 0 consultas con «concierto», «gira» o «en directo» en el GSC propio | `data/gsc_page_queries.json` | `sc-domain:entreinteriores.com`, 10-07-2026 → 02-10-2026 | 07-10-2026 | CUADRA |
| `primer disco de extremoduro` lo pelean 3 páginas (20 / 12 / 9 impresiones) | mismo fichero de GSC | mismo periodo | 07-10-2026 | CUADRA |

**No validado:** nada. Las cifras de setlist.fm no se han vuelto a descargar en esta
pasada porque ninguna ha cambiado y su validación consta arriba, con la hora de la
extracción del 6 y 7 de octubre de 2026.

### Afirmaciones nuevas de esta pasada

| ID | Afirmación | Cómo se comprueba | Evidencia | Veredicto |
|---|---|---|---|---|
| A-31 | Las marcas de los gráficos y el texto no pueden llevar el mismo granate | `dataviz/scripts/validate_palette.js` sobre `#0d0b0a` | `#e85050`+`#b08a2a` → FAIL, ΔE 2,8 deutan. `#a83a3a`+`#b08a2a` → los cinco checks PASS, ΔE 15,2 deutan / 20,1 normal | CONFIRMADA |
| A-32 | `guard_internal_links` desenlazaba el enlace al estudio | ejecutada la guarda sobre un cuerpo con los tres enlaces | antes: `unlinked: ['/estudios/repertorio-en-directo-extremoduro-robe']`. Después: solo `['/estudios/inventado']` | CONFIRMADA |
| A-33 | El relinker dominical NO se lleva el enlace al estudio | leído `relink_existing._desnudar` | solo desnuda rutas presentes en el índice del corpus (album/artist/band/concept/person/place/song/theme); `/estudios` no está | CONFIRMADA |
| A-34 | `robe plasencia` y `extremoduro caceres` ya los tiene otra página | `seo_content` en producción | `place/plasencia → "Plasencia robe"` y `place/caceres → "Cáceres extremoduro"` | CONFIRMADA |
| A-35 | Nada del sitio ataca `versiones de extremoduro` ni `conciertos de extremoduro` | `seo_content` + `posts`, `target_keyword ILIKE '%version%'`, `'%concierto%'`, `'%directo%'`, `'%gira%'` | los únicos resultados son 7 fichas de canción «en directo» y `ara malikian en concierto`: otra intención | CONFIRMADA |
