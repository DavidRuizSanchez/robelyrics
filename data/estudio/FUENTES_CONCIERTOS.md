# Fuentes para contrastar los conciertos de Extremoduro y Robe

Research del 07-10-2026. Objetivo: dejar de depender de una sola fuente para las
fechas, ciudades y recintos, y poder combinar varias.

## El problema que lo motiva

David no se creyó que Robe hubiera tocado más en Valencia (6) que en Madrid (5).
Tenía razón, y el fallo no era del dato sino de cómo se agrega:

| Causa | Efecto medido |
|---|---|
| **setlist.fm cuenta el municipio, no el área urbana** | Robe tocó 5 veces en Madrid capital **+ 2 en Rivas-Vaciamadrid + 2 en Alcalá de Henares = 9**. En Extremoduro son 29 + 10 del área (Leganés 6, Rivas, Alcalá, Pozuelo, Móstoles) = **39** |
| **Los festivales se comen la ciudad** | **13 de los 132 conciertos de Robe** no tienen ciudad: solo consta «Icónica Sevilla Fest 2024», «Bilbao BBK Live Udazkena 2021», «Gijón Life 2024»… |
| **Algún barrio cuenta como ciudad** | «Churra» (21-09-2024) es un barrio de **Murcia** |

Las tres se arreglan con fuentes externas que digan dónde fue cada cosa.

---

## Las fuentes, por orden de utilidad

### 1. Wikipedia ES — artículos de gira · **la mejor para 2013-2024**

`Categoría:Giras musicales de Extremoduro` y `Categoría:Giras musicales de Robe`
tienen artículo propio por gira, con **tabla de fechas, ciudad y recinto**:
«Para todos los públicos (gira)», «Bienvenidos al temporal (gira)», «Ahora es el
momento», «Ni santos ni inocentes».

- **Licencia CC-BY-SA**: reutilizable citando. Es la única de la lista sin zona gris.
- **Fiabilidad, medida ahora**: Wikipedia da **62 conciertos** para «Ahora es el
  momento / Ahora es cuando», **21 en 2021 y 41 en 2022**. setlist.fm da **21 y 41**.
  Coinciden a la unidad, por caminos independientes. Y para «Ni santos ni inocentes»
  Wikipedia dice 36 celebrados (3 cancelados) y setlist.fm tiene 36 en 2024.
- **Qué aporta que no tenemos**: las ciudades de los festivales. Sitúa el Festival de
  la Guitarra en **Córdoba (Teatro de la Axerquía)**, el Icónica en **Sevilla**, el
  Gijón Life en el **Parque de los Hermanos Castro**, y añade **Ponferrada
  (08-06-2024, Auditorio Municipal)**, que conviene comprobar si setlist.fm tiene.

### 2. `laleydeextremoduro.wordpress.com` — **la mejor para 1987-2002**

Entrada «EXTREMODURO: Fechas de conciertos, entradas y carteles 1988-2014».
**~400 conciertos** ordenados cronológicamente, **con fotos de las entradas físicas y
los carteles**.

- Es justo donde setlist.fm está vacío: sus fichas de 1987-2002 traen 2,2 canciones por
  concierto y muchas no traen ni repertorio.
- Empieza **antes** que setlist.fm: «Torre Lucía, 19-10-87», «Sala Por Ejemplo, Cáceres,
  23-02-89», «pub Heavy Zone, Móstoles, 30-09-89».
- **Sin licencia declarada.** Es un blog de fan. Los hechos (fecha, sitio) no son
  propiedad de nadie, pero la recopilación sí tiene valor: se usa **citándolo y
  enlazándolo**, nunca volcándolo entero. Y conviene **escribir a su autor**: una
  colaboración ahí es un backlink de los buenos y gente que comparte.
- **Una entrada escaneada es la mejor prueba documental que existe** de que un concierto
  ocurrió. Para las once canciones sin registro y para cualquier fecha dudosa, esto es
  oro.

### 3. `rockcircus.net/extremoduro-conciertos/` — **bueno para 2008-2014 y América**

~80 fechas con recinto, firmado y fechado («By Rockcircus.net, 14-12-2014»).

- **Resuelve un hueco nuestro ya**: sitúa el «RockOut 2014» en **Santiago de Chile
  (Espacio Broadway)**, que en setlist.fm sale sin ciudad.
- Detalla la gira americana de diciembre de 2014: Bogotá (Corferias), Quito (Casa de la
  Cultura), Santiago, Montevideo (Teatro de Verano), Buenos Aires (Salón Rock Sur).

### 4. Nuestro propio corpus — **exclusivo, y ya pagado**

Medido hoy: **199 fechas completas** del tipo «12 de mayo de 1996» repartidas por el
corpus (177 en transcripciones de YouTube), y **129 transcripciones que son capítulos
de concierto o de gira** de la historia de Extremoduro de Juancares.

Hay material que no existe en ninguna base de datos: «AUDIO INÉDITO CONCIERTO DE
EXTREMODURO EN ALCALÁ DE HENARES EN 1993», «CAPÍTULO 14. EL PRIMER CONCIERTO GORDO DE
EXTREMODURO (1991)», «CAPÍTULO 34: EXTREMODURO EN MATAVENERO (1994)».

Más los **45 conciertos de `video_assets`**, con fecha y lugar extraídos solo de
evidencia literal (de 1992-04-17 a 2024-11-09, 33 canales).

Es material de un TERCERO: se cita atribuido, como ya se hace con el consultorio en el
registro de afirmaciones. Y las transcripciones son automáticas: traen erratas.

### 5. Prensa — para fijar una fecha concreta

Mondo Sonoro, Infobae, prensa local (HOY, El Periódico de Extremadura) publican el
listado de fechas al anunciarse cada gira. Útil para **verificar un dato suelto**, no
para volumen. (El veto a Mondo Sonoro / Efe Eme / Rockdelux es solo para el corpus:
como fuente de verificación externa y como diana de outreach son legítimos.)

---

## ⚠️ Songkick y Bandsintown: NO sirven, y está medido

Songkick (`artists/217469-extremoduro`) y Bandsintown (`a/73431-extremoduro`) parecen la
solución obvia. No lo son:

**Conservan las fechas anunciadas que luego se cancelaron.** La gigografía de Songkick
lista para 2020 conciertos en Rivas-Vaciamadrid (×4), Bilbao (Kobetamendi), Barcelona
(Parc del Fòrum ×2), Cáceres, Santiago de Compostela y Sevilla (La Cartuja)…
**ninguno ocurrió**: la gira de despedida se anunció en diciembre de 2019, se aplazó
por la covid y se **canceló el 25-08-2021** (y el grupo ya se había disuelto el
18-12-2019).

setlist.fm, en cambio, tiene **cero** conciertos de Extremoduro en 2020, que es lo
correcto, porque solo registra lo que se tocó.

→ Usar Songkick para «cuántas veces tocaron en X» **añadiría una decena de conciertos
fantasma**, y encima de la gira más vendida de su historia, que es donde más llamaría
la atención. Queda descartado para conteo; sirve, con cuidado, para pistas de recinto.

(`concertarchives.org` devuelve **403** a una petición normal. No se insiste.)

---

## Plan de combinación propuesto

La regla: **una fuente nunca sobrescribe a otra en silencio.** Cada concierto guarda de
dónde sale cada campo, y las discrepancias se publican.

1. **Espina dorsal**: setlist.fm, que es la única con los 591 conciertos y está
   corroborada por Wikipedia en las dos giras comprobadas.
2. **Resolver las 23 ciudades vacías** con Wikipedia y Rock Circus, campo a campo.
3. **Área urbana como dimensión APARTE**, nunca sustituyendo al municipio: se publica
   «Madrid capital 5» y «área de Madrid 9», no un 9 llamado «Madrid». Agregar sin
   decirlo es lo que hizo que Valencia pareciera por delante.
4. **Extender hacia atrás** con `laleydeextremoduro` para 1987-2002, marcando cada
   concierto que solo tenga esa fuente.
5. **Nuestro corpus como tercera opinión** para fechas y anécdotas, atribuido.
6. **Lo que solo tenga una fuente se marca como tal.** Un concierto documentado por tres
   fuentes y otro por un blog no valen lo mismo, y el entregable lo tiene que decir.

### Lo que NO se hace

- No se vuelca ninguna recopilación ajena entera: se cuenta sobre ella y se enlaza.
- No se cuentan conciertos cancelados como celebrados.
- No se funden municipios bajo el nombre de la capital sin declararlo.
- No se rellena una ciudad «por parecido» con el nombre del festival: o lo dice una
  fuente, o se queda vacía.
