# Ideas de Digital PR y backlinks — ola 2 en adelante

Documento interno (09-10-2026). Complementa lo que ya está en marcha: estudio del repertorio en directo, outreach a 17 medios y creadores, y la ola del aniversario del 10 de diciembre. Nada de aquí repite ese pitch.

Cada cifra lleva su fuente en la sección final. Lo que no está medido va como `[HIPÓTESIS]`.

---

## Punto de partida (medido)

**El sitio, prácticamente sin enlaces**
- **DR 4,7** (Ahrefs, 09-10-2026).
- De los dominios que enlazan, los no marcados como spam son 8:
  - 4 son granjas `.shop` / `.store` sin dofollow;
  - 1 es la web propia, `davidruizsanchez.es`;
  - quedan 3 ajenos sin valor editorial: `bisprofit.com` y `despaansewiki.nl` (dofollow) y `edgechat.ai` (sin dofollow).
- El resto del perfil es spam automático de SEO.
- Conclusión: **cualquier enlace editorial real mueve la aguja**. No hace falta desautorizar el spam (Google lo ignora); lo que hace falta son enlaces buenos.

**Lo que busca la gente**

GSC del 10-jul al 2-oct-2026, 1.846 consultas, 35.015 impresiones.

| Tema | Consultas | Impresiones | Clics |
|---|---:|---:|---:|
| «letra» | 312 | 5.330 | 34 |
| «significado / qué significa» | 158 | 3.335 | 42 |
| «frases / citas» | 34 | 236 | 8 |
| conciertos, poemas, libros, acordes | ≤10 cada uno | ≤22 cada uno | 0 |

La demanda está en **qué quiere decir esto**. Las ideas que mejor encajan con el SEO son las que explican letras, no las de datos de directo.

**Material propio que nadie más tiene** (prod, 09-10-2026)
- **Letras**: 153 fichas de canción y **7.039 versos** en la BD.
- **Entrevistas con marca de tiempo**: **8.280 tramos de transcripción en 18 fuentes**. Se puede enlazar al segundo exacto de un vídeo donde Robe dice algo.
- **Corpus** por tipo de fuente:

  | Tipo | Fuentes |
  |---|---:|
  | Transcripciones de YouTube | 380 |
  | Comentarios de YouTube | 145 |
  | Anotaciones de Genius | 122 |
  | Entrevistas a Robe | 18 |
  | Citas de Robe | 12 |
  | Libros | 14 |

- **Autorías**: 13 créditos aplicados en 12 canciones (Chinato, Machado, Neruda, Lorca, Sor Kampana…), más **6 hipótesis sin corroborar** (Marcos Ana ×2, Miguel Hernández, Santos Isidro Seseña ×2, Shakespeare/Zorrilla).
- **Grafo de entidades**: 595 aristas; 48 personas y 5 libros.

---

## A. Campañas creativas (enlace por mérito)

Van ordenadas por la relación entre lo que pueden dar y lo que cuestan.

### 1. «Robe, en sus palabras»: el archivo de lo que dijo, al segundo
**Concepto**
- Un índice por temas (la poesía, Plasencia, las drogas, dejar Extremoduro, la muerte…).
- Cada entrada es una frase corta de Robe con fecha, medio y enlace al **segundo exacto** del vídeo original.
- No se reproduce la entrevista: se indexa y se manda tráfico a la fuente.

**Por qué engancha**
- Desde su muerte, el fan quiere oírle a él, no a quien habla de él.
- Nadie ha ordenado eso: hoy está desperdigado en horas de vídeo.

**Material**
- `source_segments` (8.280 tramos con tiempo).
- `robe_interview` (18) y `robe_quote` (12).

**A quién se pitchea**
- Periodistas que escriben del aniversario: «de dónde sale esta cita» es su problema diario.
- Los canales cuyos vídeos se enlazan (ganan visitas y suelen devolver la mención).
- Wikipedia ES, como fuente de citas fechadas.

**Riesgo**
- Las transcripciones automáticas traen erratas («Robben y Niesta»).
- **Cada frase se revisa escuchándola**: es la regla que ya rige el consultorio, nunca se cita la transcripción a ciegas.
- Esfuerzo medio.

### 2. «El poeta que quizá no existe»: la investigación abierta de las autorías
**Concepto**
- Pieza sobre los poetas que Robe metió en sus letras. Los confirmados van como dato; las 6 hipótesis van **como pregunta abierta**.
- Gancho: Santos Isidro Seseña, a quien Jot Down atribuye «La mala gana». Un comentario del propio artículo sugiere que podría ser un seudónimo de Robe.
- Se pide ayuda al lector, a filólogos y a bibliotecas para confirmar o descartar cada caso.

**Por qué engancha**
- Misterio, más literatura, más una comunidad que se siente parte del hallazgo.
- Cada confirmación que llegue es una actualización con su nota de prensa.

**Material**
- `data/song_credits.yaml`, incluidas las notas con versos y libros concretos.

**A quién se pitchea**
- Jot Down (de su artículo de 2017 salen las pistas).
- Prensa cultural, blogs de poesía y la Fundación Miguel Hernández.
- Para Marcos Ana: asociaciones de memoria histórica.

**Riesgo**
- Nunca presentar una hipótesis como hecho. La pieza vive de decir «no consta».
- Esfuerzo bajo-medio.

### 3. «Extremoduro en clase de Lengua»: fichas didácticas CC BY
**Concepto**
- Fichas descargables de comentario de texto para bachillerato y ESO: la letra completa enlazada, recursos literarios señalados, contexto y el poema de origen cuando lo hay.
- Licencia CC BY, el mismo esquema que el CSV del estudio.

**Por qué engancha**
- El profesorado de Lengua ya usa canciones en clase.
- Los recursos educativos se enlazan durante años desde blogs docentes, CEP y webs de departamento.

**Material**
- Los 13 créditos verificados (Machado, Neruda y Lorca son temario).
- 153 fichas de canción.

**Demanda**
- «significado» suma 158 consultas y 3.335 impresiones.

**Riesgo**
- Las letras tienen derechos de autor. La ficha **enlaza** a nuestra letra y cita fragmentos breves para comentarlos; no reproduce letras enteras en el PDF.
- Esfuerzo medio.

### 4. «¿Qué canción de Extremoduro eres?»
**Concepto**
- Test de 6-8 preguntas. Las respuestas se convierten en un vector, y sale la canción más cercana con su verso y una tarjeta para compartir.
- Usa los embeddings que ya existen.

**Por qué engancha**
- Formato que se comparte solo en redes y foros.
- Encaja con una cuenta de IG de 125 seguidores que necesita alcance.

**Material**
- Colecciones `lines_v1` y `lyrics_full_v1` de Qdrant.

**A quién**
- Comunidad fan y medios de entretenimiento musical, del tipo «hemos hecho el test».

**Riesgo**
- Bajo. Más alcance social que enlaces: los enlaces llegan de rebote.
- Esfuerzo bajo-medio.

### 5. «La Extremadura de las canciones»
Reformula la idea del mapa de lugares, que no se sostenía (ver abajo).

**Concepto**
- Pieza para prensa extremeña y turismo con lo que sí consta:
  - Cáceres aparece en 18 versos;
  - Badajoz en 10;
  - Monfragüe en 4;
  - Plasencia en 2;
  - el Jerte en 1.
- Se cruza con el dato del estudio (Cáceres, segunda provincia en conciertos) y con los lugares de la biografía.
- Se puede añadir una ruta por Plasencia.

**A quién**
- Medios extremeños: ya hay relación con El Periódico de Extremadura.
- Turismo de Extremadura, Ayuntamiento de Plasencia, Diputación de Cáceres.

**Medido**
- `song_places` solo tiene 11 lugares.
- Buscando topónimos en los 7.039 versos, **solo 6 fichas de canción nombran alguno** (Extremaydura y Pepe Botika con sus versiones, ¡Qué borde era mi valle! y ¡Qué sonrisa tan rara!).
- **Por eso no hay «mapa de España cantado»**: no hay material para eso.
- Esfuerzo bajo.

### 6. Estudio v3: cómo cambió su vocabulario de 1987 a 2024
**Concepto**
- Riqueza léxica, palabras que aparecen y desaparecen, y el paso de Extremoduro a Robe en solitario.
- Periodismo de datos con gráficos, igual que el estudio actual.

**Material**
- `lines` en la BD.

**Estado**
- `[HIPÓTESIS]`: no se ha medido si sale una historia con titular.
- Hay que medirlo antes de prometer nada. Hay que usar las 132 composiciones canónicas, no las 153 filas, o se repite el error del verso más repetido (ver gotcha de composiciones canónicas).
- Esfuerzo medio.

### 7. Co-creación con Tesônica: «La ley innata, visualizada»
**Concepto**
- Tesônica ya publicó el análisis armónico exhaustivo de La ley innata, que no existe en ninguna otra fuente.
- Nosotros ponemos la capa visual: motivos conductores, estructura y letra sincronizada. Ella la difunde.

**Por qué funciona**
- Enlace natural desde su canal y su comunidad.
- Pieza única en internet.

**Riesgo**
- Depende de que acepte.
- Esfuerzo medio.

### 8. Ampliación de lo ya previsto
- **Muro del aniversario** (10-dic): «la primera vez que los vi», casado con el concierto real del dataset propio de conciertos.
  - El tope para pitchear sigue siendo mediados de noviembre.
- **«Yo estuve»**: archivo colectivo de entradas y carteles.
  - Pedir permiso antes al blog laleydeextremoduro, que tiene un catálogo ya localizado.

---

## B. Backlinks clásicos (ejecutables ya)

1. **Wikipedia ES**: citar el estudio en los artículos de las giras. Ya estaba propuesto y sigue pendiente. Es el enlace más fácil de conseguir con mérito.
2. **Menciones sin enlace**: pasar el skill `menciones-sin-enlace` sobre «Entre Interiores» y «entreinteriores» tras la campaña del estudio, y `sentimiento-menciones` antes de pedir nada.
3. **Recuperar menciones del outreach**: si algún medio publica sin enlazar, pedir el enlace citando la licencia CC BY, que exige atribución.
4. **Enlaces rotos**: buscar con Ahrefs webs de fans y fanzines caídos que la gente todavía enlaza, y ofrecer nuestra ficha equivalente. `[HIPÓTESIS]`: no se ha medido cuántos hay.
5. **Páginas de recursos**: webs de fans, foros y bandas tributo con secciones de «enlaces». Ofrecer el CSV y las fichas.
6. **Autores de los 5 libros** de /libros: reseña o entrevista y avisarles; suelen enlazar lo que habla de su libro.
7. **Repositorios universitarios**: TFG y tesis sobre Extremoduro. Ofrecer el dataset CC BY como fuente citable.
8. **Podcasts y radio**: David como invitado para contar el estudio y las autorías (la idea 2 da tema de conversación).
9. **Peticiones de periodistas** en plataformas tipo HARO, sobre rock y música española.
10. **Ojo con los widgets**: un widget de efemérides embebible puede dar enlaces, pero solo con anclas naturales. Uno con anclas forzadas es un esquema de enlaces para Google.

---

## Orden recomendado
1. Wikipedia ES y menciones sin enlace (B1, B2): cuestan poco y ya.
2. Idea 2 (poeta que quizá no existe) e idea 5 (Extremadura): poco esfuerzo, gancho de prensa y llegan antes del 10-dic.
3. Idea 1 (Robe en sus palabras) para el aniversario: es la de más valor.
4. Ideas 3 y 4 en invierno: son evergreen.
5. Idea 6 solo si la medición da titular.

---

## Fuentes

Extracción del 09-10-2026.

| Dato | Fuente | Periodo / filtro | Cómo |
|---|---|---|---|
| DR 4,7 | Ahrefs `site-explorer-domain-rating` | 2026-10-09 | target `entreinteriores.com` |
| 8 dominios no spam y su detalle | Ahrefs `site-explorer-referring-domains` | live, `is_spam = false`, subdomains | consulta del 09-10-2026 |
| 1.846 consultas · 35.015 impr. · temas | `data/gsc_queries.json` | 12 semanas (≈10-jul → 02-oct-2026; generado el 05-10 por `gsc_fetch_page_queries --weeks 12`, desfase 3 días) | regex por tema sobre `query`, suma de `impressions` y `clicks` |
| 153 canciones · 7.039 versos · 595 aristas · 48 personas · 5 libros | BD prod | 09-10-2026 | `count(*)` de `songs`, `lines`, `entity_edges`, `persons`, `books` |
| Fuentes del corpus por tipo | BD prod `interpretation_sources` | 09-10-2026 | `group by kind` |
| 8.280 tramos en 18 fuentes | BD prod `source_segments` | 09-10-2026 | `count(*)`, `count(distinct source_id)` |
| 13 créditos en 12 canciones | BD prod `song_credits` | 09-10-2026 | `count(*)`, `count(distinct song_id)` |
| 6 hipótesis de autoría | `data/song_credits.yaml` | `status: hipotesis` | test `test_las_seis_hipotesis_no_entran_al_barrido` |
| 11 lugares en `song_places` | BD prod | 09-10-2026 | `count(distinct place_id)` |
| Topónimos en letras (Cáceres 18, Badajoz 10, Monfragüe 4, Plasencia 2, Jerte 1, Extremadura 1; 6 fichas) | BD prod `lines` | 42 topónimos probados por palabra completa | regex `\b<lugar>\b` sobre `lines.text` |
| Cáceres segunda provincia | Estudio publicado / `OUTREACH_EXTREMADURA.md` | — | no re-derivado aquí: se cita del estudio |
| 125 seguidores en IG | memoria del proyecto (campaña de PR) | — | **no validado** hoy contra la API de Meta |

**Validación**
- Las cifras de la tabla se han sacado en esta misma sesión de su fuente (API o BD). No se ha copiado ninguna de un documento anterior.
- Excepciones marcadas: los 125 seguidores de IG (no validado) y el dato de Cáceres, que se cita del estudio.
