# Assets SEO alrededor del estudio, y qué NO se puede coger

Encargo de David (07-10-2026): «busca unos seo assets que no canibalicen con el
post ni nada de la web, pero que tengan gancho (y si puede ser que ataquen a algo
con búsquedas, pero no es prioritario)».

Este documento es el resultado de medirlo, no de estimarlo. **Todo volumen sale de
Ahrefs Keywords Explorer, país España, consultado el 07-10-2026.** La propiedad de
cada término sale de dos sitios: `seo_content.target_keyword` y `posts.target_keyword`
en producción (consultados el 07-10-2026), y el GSC propio del sitio
(`data/gsc_page_queries.json`, `sc-domain:entreinteriores.com`, 10-07-2026 a
02-10-2026). Donde no hay dato, va `—`.

---

## El hallazgo que cambia el encargo

**En todo el GSC del sitio no hay una sola consulta con «concierto», «gira» o «en
directo».** Cero. Lo que sí hay son 102 consultas con palabras geográficas, y las de
arriba son todas «de dónde es Extremoduro» sobre `/extremoduro` (356 impresiones,
posición 8,3).

Y el tema, medido, **casi no tiene búsquedas**. Trece términos consultados dan 0:
`setlist extremoduro`, `extremoduro en directo`, `repertorio extremoduro`,
`canciones mas tocadas extremoduro`, `extremoduro curiosidades`, `extremoduro en
cifras`, `cuantos conciertos ha dado extremoduro`, `donde toco extremoduro`,
`extremoduro provincias`, `extremoduro primer concierto`, `extremoduro numero de
conciertos`, `versos de extremoduro`, `estribillos de extremoduro`.

Conclusión honesta: aquí **el gancho no puede venir del volumen, porque no hay**.
El estudio capta por enlaces, menciones y marca, no por búsqueda. Lo que sigue
ordena lo poco que hay con volumen y lo separa de lo que ya es de otro.

---

## Lo que YA es de otra página: no se toca

| Término | Vol/mes | Quién lo tiene | Evidencia |
|---|---|---|---|
| `robe plasencia` | **200** | `/lugares/plasencia` | `seo_content.target_keyword = "Plasencia robe"` |
| `letras de extremoduro` | **150** | las 99 fichas de canción | `target_keyword` por canción («Desarraigo letra: …») |
| `extremoduro caceres` | **30** | `/lugares/caceres` | `seo_content.target_keyword = "Cáceres extremoduro"` |
| `discografia de extremoduro` | 40 | `/discografia/extremoduro` | ruta estática en el sitemap, prio 0,9 |
| `extremoduro plasencia` | 10 | `/lugares/plasencia` + `/extremoduro` | GSC: 10 impresiones, posición 12-14 |

**`extremoduro caceres` era el candidato obvio** (el titular del estudio es que
Cáceres suma 37 conciertos, por delante de Barcelona con 33) y está cogido. Por eso
no se crea página: se AMPLÍA la que ya existe (ver abajo).

### Y una canibalización que ya existe, anterior a esto

`primer disco de extremoduro` (50/mes) lo pelean **tres** páginas en el GSC propio:
`/extremoduro/rock-transgresivo` (20 impresiones, pos 19,5), `/discografia/extremoduro`
(12, pos 31,6) y `/discografia` (9, pos 39,0). No es de este estudio y no se arregla
aquí, pero queda anotado: es un caso de libro para `seo_opportunities`.

---

## Lo que está libre (y tiene gancho)

### A-1 · Ampliar `/lugares/caceres` y `/lugares/plasencia` con los conciertos

**No es una página nueva: es la vía con mejor relación gancho/riesgo.** Las dos
fichas existen, ya tienen su término, y hoy hablan solo de cómo aparece la ciudad en
las letras. El estudio les añade un dato que no tienen nadie: Cáceres es la **segunda
provincia** del país en conciertos documentados (37, por delante de Barcelona), y
Plasencia suma **11**.

- Canibalización: **cero por construcción**, no hay URL nueva.
- Vía: `scripts.seo.augment_entity --gap-hint`, que es el motor de ampliación sin
  pérdida que ya existe. No regenerar: ampliar.
- Volumen que ya capta el par: `robe plasencia` 200 + `extremoduro caceres` 30.

### A-2 · «Las versiones que tocaban Extremoduro y Robe en directo»

El único término con volumen medido que **nadie** del sitio tiene.

- `versiones de extremoduro` · **10/mes** · ninguna página lo declara (comprobado
  contra `seo_content` y `posts`: los únicos `target_keyword` con «version» son de
  fichas de canción en directo, que es otra intención).
- Material propio, ya contado en el estudio: «Versiones y otros» son **170
  interpretaciones en Extremoduro (5,2 %) y 667 en Robe (29,2 %)**, y una versión
  ajena, *Rockin' All Over the World*, entra en el top 14 del repertorio.
- Gancho: que **el 29,2 % de lo que tocaba Robe no salía de sus cuatro discos** es
  un dato que se discute solo.

### A-3 · `conciertos de extremoduro` (30/mes): se puede reclamar, pero es decisión tuya

El término lo tiene nominalmente el post
`el-fenomeno-insuperable-de-los-conciertos-de-extremoduro-y-robe`, que **tiene
`target_keyword` a NULL y capta 0 impresiones** por cualquier consulta de conciertos.
El estudio es objetivamente la mejor respuesta a esa búsqueda (591 conciertos, mapa,
año a año).

Pero dos páginas sobre los conciertos de Extremoduro **son canibalización**, que es
justo lo que pediste evitar. Así que esto **no se ha hecho** y hay tres salidas, por
orden de preferencia:

1. Redirigir el post viejo al estudio y que el estudio tome el término.
2. Reenfocar el post viejo a otra cosa (habla del fenómeno social, no del dato).
3. Dejarlo como está y que el estudio no persiga ese término.

### A-4 · Gancho sin volumen: se publican por enlaces, no por búsqueda

Medidos a **0/mes**, y aun así son lo que un periodista o un fan cita. Van como
secciones del estudio, nunca como páginas propias, porque una página con 0 búsquedas
y poco cuerpo es una página delgada:

- el setlist de las once que nunca sonaron (ya es la pieza de cabecera);
- el ranking de lo más tocado y lo que se dejó de tocar;
- el último concierto de Extremoduro (`ultimo concierto de extremoduro`, **10/mes**,
  nadie lo tiene: es el único de este grupo con algo de volumen).

---

## Qué NO se recomienda, y por qué

- **Una página por provincia.** 50 páginas de 1 a 48 conciertos cada una, sin
  búsquedas y sin cuerpo propio. Es doorway, y además compite con `/lugares`.
- **Una página «Extremoduro en cifras».** `extremoduro en cifras` y `extremoduro
  curiosidades` dan **0**, y el contenido sería el estudio otra vez con otra URL.
- **Tocar `primer disco de extremoduro`.** Ya lo pelean tres páginas nuestras: meter
  una cuarta empeora lo que hay.

---

## Trazabilidad

| Dato | Fuente | Periodo / filtro | Consultado |
|---|---|---|---|
| Volúmenes de los 39 términos | Ahrefs Keywords Explorer (`keywords-explorer-overview`) | país `es` | 07-10-2026 |
| `target_keyword` de los 26 posts publicados | `posts` en producción | `status='published'` | 07-10-2026 |
| `target_keyword` de fichas SEO | `seo_content` en producción | `published is true` | 07-10-2026 |
| 102 consultas geográficas y sus páginas | `data/gsc_page_queries.json` | `sc-domain:entreinteriores.com`, 10-07-2026 → 02-10-2026 | 07-10-2026 |
| Interpretaciones de «Versiones y otros» | `data/estudio/SOURCES.md` (ver ledger) | 591 setlists, 1987-2024 | 06/07-10-2026 |

**Un término que Ahrefs devuelve a 0 no es «sin búsquedas»: es «sin búsquedas
medidas por Ahrefs en España».** Ahrefs omite de la respuesta los términos que no
reconoce, así que los trece de arriba se consultaron y volvieron vacíos o con
`volume: 0`; ninguno se ha estimado.
