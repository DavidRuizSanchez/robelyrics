# Post #65 «Flores Amarillas 2027»: corrección del 16-11-2026, fuentes y registro de afirmaciones

URL: `https://entreinteriores.com/blog/flores-amarillas-2027-tributo-a-robe-en-plasencia`
(posts.id=65, propuesta #404). Versión anterior guardada en `content_revisions`
(target_kind=`post`, reason «corrección de veracidad…»).

## Qué estaba mal (comprobado contra su artículo, laguiago.com, descargado el 16-11-2026 10:22 UTC)

| ID | Lo que decía el post | Qué dice la fuente | Veredicto |
|---|---|---|---|
| E-01 | «Entre los músicos confirmados se encuentra Fito Cabrales» | No nombra a ningún músico | Inventado |
| E-02 | «la participación de Kutxi Romero, líder de Marea» | No lo nombra | Inventado |
| E-03 | «una actuación especial de Los Robe, un grupo tributo» | No lo nombra | Inventado |
| E-04 | «actuaciones de músicos que compartieron escenario con Robe» | No lo dice | Inventado |
| E-05 | «guiños a… "Si te vas..."» | No lo dice | Inventado |
| E-06 | «El evento, denominado Primeras Flores Amarillas» | «esta segunda entrega perderá el término inicial» | Falso |
| E-07 | meta_description: «con actuaciones de grandes artistas» | No lo dice | Inventado |
| E-08 | Hero: banda tributo «Extremoband» (ticketere.com) | Foto de otro evento | Falso |

El gate nuevo (`source_grounding`, con el juez real) lo caza todo: E-01 a E-05 bloquean.
Fixture: `api/app/tests/fixtures/flores_amarillas_2027.json`.

## Fuentes (todas descargadas con `article_extract.fetch_article` el 16-11-2026)

| F | Medio · URL | Hora UTC | Estado |
|---|---|---|---|
| F1 | laguiago · https://www.laguiago.com/espana/flores-amarillas-2027-plasencia-festival-homena-robe-iniesta/ | 10:22:25 | ok, 1.947 car. |
| F2 | MariskalRock · https://mariskalrock.com/actualidad/flores-amarillas-homenajeara-de-nuevo-a-robe-extremoduro-con-una-segunda-edicion-que-vuelve-a-apostar-por-el-talento-emergente/ | 10:22:25 | ok, 2.762 |
| F3 | COPE · https://www.cope.es/emisoras/extremadura/caceres-provincia/plasencia/noticias/plasencia-vuelca-nuevo-robe-festival-flores-amarillas-triplica-apuesta-2027-20261115_3474505.html | 10:22:25 | ok, 2.574 |
| F4 | La Portada de Extremadura · https://www.laportadadeextremadura.com/vida/ocio/plasencia-prepara-flores-amarillas-2027-mantener-vivo-legado-robe_7586_102.html | 10:22:26 | ok, 2.589 |
| F5 | Planvex · https://planvex.es/web/2026/11/festival-flores-amarillas-2027-plasencia/ | 10:22:27 | ok, 1.479 |
| F6 | Córdoba Rock · https://cordobarock.es/festival-flores-amarillas-2027-plasencia-robe/ | 10:22:29 | ok, 2.553 |
| F7 | Metal Bizarre · https://metalbizarre.com/2026/11/13/flores-amarillas-celebrara-su-segunda-edicion-en-homenaje-a-robe-iniesta-con-20-bandas-emergentes/ | 10:22:32 | ok, 3.573 |
| F8 | Vivir Ediciones (fuente: Diputación de Cáceres) · https://vivirediciones.es/plasencia-festival-flores-amarillas-segunda-edicion-mayo/ | 10:22:32 | ok, 1.240 |
| F9 | Modo Festival · https://modofestival.es/flores-amarillas-2027-plasencia-homenaje-robe-20-bandas-acampada/ | 10:22:32 | ok, 4.741 |
| F10 | Europa Press (nota de la Junta) · https://www.europapress.es/extremadura/noticia-veintena-bandas-emergentes-participaran-festival-homenaje-robe-iniesta-15-mayo-plasencia-20261112122510.html | 10:22:33 | ok, 1.466 |
| F11 | Cartel oficial 2027 (imagen) · https://img.europapress.es/fotoweb/fotonoticia_20261112122510_1200.jpg | 16-11-2026 | leído a mano |

Regla aplicada: cada dato, en 2 o más fuentes, o en una oficial (F10, F11).
Ningún medio se nombra en el post («La voz es nuestra»).

## Registro de afirmaciones del post corregido

| ID | Afirmación (tal cual en el post) | Fuentes y cita literal | Veredicto |
|---|---|---|---|
| A-01 | sábado 15 de mayo de 2027 | F3 «La cita tendrá lugar el próximo 15 de mayo de 2027»; F5 «se celebrará el sábado 15 de mayo»; F11 «15 Mayo» | CONFIRMADA |
| A-02 | Es el sábado más cercano al 16 de mayo, el día en que nació en la ciudad | F6 «el sábado más cercano al 16 de mayo, día en que nació Robe en la propia Plasencia»; F10 «nacido un 16 de mayo en esta localidad» | CONFIRMADA |
| A-03 | desde esta edición el festival se celebrará siempre en esa fecha | F10 «establece a partir de ahora como fecha de celebración el sábado más cercano al 16 de mayo»; F6 «un criterio que la organización mantendrá en las próximas ediciones» | CONFIRMADA |
| A-04 | Los conciertos serán gratuitos y el encuentro sigue siendo sin ánimo de lucro | F10 «todos los conciertos serán de acceso gratuito»; F7 «sin ánimo de lucro»; F11 «Festival gratuito» | CONFIRMADA |
| A-05 | El cartel lo formarán veinte bandas emergentes, frente a las cinco de la primera edición | F3 «pasando de cinco a 20 bandas emergentes»; F7 «Frente a las cinco formaciones que participaron en la primera convocatoria»; F11 «20 Bandas Emergentes» | CONFIRMADA |
| A-06 | saldrán de un concurso abierto | F3 «seleccionadas mediante un concurso abierto»; F11 «Seleccionadas por concurso» | CONFIRMADA |
| A-07 | Las bases aún no se han publicado, así que a día de hoy no hay ningún grupo anunciado | F3 «La organización anunciará próximamente las bases»; F9 «Las bases todavía no se conocen» (si se eligen por concurso y no hay bases, no hay grupos) | CONFIRMADA |
| A-08 | La organización las dará a conocer en su Instagram, @floresamarillas.festival, y en una web propia que todavía no está activa | F3 «su perfil de Instagram, @floresamarillas.festival, y en una nueva página web que se habilitará»; F9 «una página web que aún no está activa» | CONFIRMADA |
| A-09 | Habrá tres escenarios | F3 «tres escenarios»; F11 «3 Escenarios» | CONFIRMADA |
| A-10 | Dos estarán en el centro histórico, previsiblemente en el entorno de la Catedral y de la Plaza Mayor, para los conciertos de mañana y tarde | F3 «dos en el centro histórico, en el entorno de la Catedral y la Plaza Mayor, para las actuaciones de mañana y tarde»; F6 «previsiblemente en el entorno de la Catedral y en la Plaza Mayor» | CONFIRMADA (se mantiene el «previsiblemente») |
| A-11 | El tercero, en el recinto ferial, acogerá los de la noche | F3 «un tercero en el recinto ferial para los conciertos nocturnos»; F5 «Los de la noche tendrán lugar en el recinto ferial» | CONFIRMADA |
| A-12 | talleres artísticos abiertos al público y gratuitos, de batucada, grafiti, danza o pintura, que se elegirán igualmente por concurso | F3 «talleres artísticos de batucada, grafiti, danza o pintura… también se seleccionarán por concurso»; F5 «abiertos al público gratuitamente» | CONFIRMADA |
| A-13 | acampada libre y una zona camper | F8 «acampada libre… zona camper»; F9 «acampada libre y zona camper»; F11 «Acampada libre · Zona Camper» | CONFIRMADA |
| A-14 | apoyo de la Junta de Extremadura, la Diputación de Cáceres y el Ayuntamiento de Plasencia | F3 «cuenta con el respaldo de la Junta de Extremadura, la Diputación Provincial de Cáceres y el Ayuntamiento de Plasencia»; F11 (logos) | CONFIRMADA |
| A-15 | nace de la implicación de la familia de Robe y de la propia ciudad | F4 «nace de la implicación de la familia del músico, de la ciudad de Plasencia»; F1 «la familia del artista» | CONFIRMADA |
| A-16 | Deja atrás el «Primeras» con el que se presentó en 2026 y llega con más inversión que entonces | F4 «perderá precisamente la palabra «Primeras»… con una mayor inversión»; F1 «presupuesto reforzado» | CONFIRMADA |
| A-17 | La primera se celebró el 16 de mayo de 2026 | F6 «La primera edición se celebró el 16 de mayo de 2026»; F4 «celebrada el pasado 16 de mayo» | CONFIRMADA |
| A-18 | reunió a más de 15.000 personas | F1 «Más de 15.000 personas»; F4 «más de 15.000 personas» | CONFIRMADA (cifra difundida tras la jornada; se escribe así) |
| A-19 | con el escenario principal en Torre Lucía | F1 «El recinto de Torre Lucía»; F4 «Torre Lucía acogió el escenario principal» | CONFIRMADA |
| A-20 | una docena de rincones acústicos por el casco histórico | F1 «Una docena de rincones acústicos»; F4 «una docena de rincones acústicos» | CONFIRMADA |
| A-21 | Tocaron cinco bandas emergentes, Aljamia, Oxygen, Chula, Carameloraro e Illo Brown! | F6 y F9 «Aljamia, Oxygen., Chula, Carameloraro e Illo Brown!»; post #1 | CONFIRMADA |
| A-22 | un mural dedicado a Robe y al poeta Manolo Chinato, junto al que se plantaron flores | F3 «un mural dedicado a Roberto Iniesta y al poeta Manolo Chinato, junto al que se realizó una plantación colectiva de flores»; F9 «un mural dedicado a Robe y al poeta Manolo Chinato» | CONFIRMADA |

### Discrepancias que no entran en el post

- **Asistencia en Torre Lucía**: F1 y F4 dicen «alrededor de 5.000»; nuestro post #1 dice «5.000
  pulseras… aforo solo para 2.000». No cuadran, así que la cifra no se da.
- **Edad de Robe**: F2 dice que habría cumplido «64 años»; nació el 16-05-1962, así que el
  16-05-2027 serían 65 (F9 lo dice bien). No se usa.
- **Nombre del recinto ferial** («del Berrocal»): solo F5. No se usa.
- **«por primera vez» acampada**: solo F9. No se usa.

### Hero

Cartel oficial de 2027 (F11): logos de la Junta de Extremadura, la Diputación de Cáceres y el
Ayuntamiento de Plasencia, con pie de Europa Press «Cartel del II Homenaje Oficial a Robe
Iniesta en Plasencia - JUNTA DE EXTREMADURA». Se re-aloja en Cloudinary. El de Cultura Plasencia
que usaba la propuesta #533 es **el de 2026** («Primeras», 16 de mayo, Torre Lucía): descartado.

## Validación

- 16-11-2026: gates sobre la versión nueva en local: `source_grounding` (juez real) ok,
  `source_guard` sin fuentes nombradas, `lyric_guard` sin bloqueos, `seo_style` title, H1,
  description y headings ok, `editorial_review` 78 («revise» por repetición léxica, sin
  objeciones de hechos).
- Coherencia número ↔ lista: A-05 (20 y 5) y A-21 (5 nombres) cuadran.
- 16-11-2026 12:05 UTC, en prod (PR #133 desplegado): dry-run de `corregir_post.py` limpio
  (source_grounding, source_guard y lyric_guard); `--apply --descartar-propuesta 533` a las
  12:05:41. Copia previa en `content_revisions` id 1523; propuesta #533 → `discarded`; hero
  re-alojado en Cloudinary (`y15tlgr2kn0awlbugyyk.jpg`).
- 16-11-2026 ≈12:07 UTC, URL pública por Cloudflare y por origen (`--connect-to`): 200; 0
  apariciones de «Fito», «Kutxi», «grandes artistas», «ticketere»; «Los Robe» solo en el menú
  de la web; `og:image` y meta description nuevas; `NewsArticle.headline` = title nuevo.
- 16-11-2026 12:39 UTC, a petición de David: fuera la nota de corrección del final del cuerpo
  (`content_revisions`, reason «quitar la nota de corrección») y `published_at` pasa de
  2026-10-12 08:54 a 2026-11-16 12:39 UTC. Comprobado en la URL pública: sin la nota y con
  `datePublished` 2026-11-16T12:39:14Z.
- 16-11-2026 ≈13:48 UTC: el hero re-alojado (`y15tlgr2kn0awlbugyyk.jpg`, 1080×1080) era un
  RECORTE del cartel: `_rehost_to_cloudinary` pasa por `imaging._fetch_image`, que corta a
  cuadrado para Instagram, y se perdía el «15 Mayo». Re-subido el original de Europa Press
  (1200×1600) sin recortar: `pkb1qahwxxxcwypk2ae2.jpg`, servido en la URL pública.
- 16-11-2026, `audit_jsonld --linea-base`: 389 URLs con 200, 0 fallos nuevos, 0 páginas pierden
  algo frente a la línea base del 13-11.
