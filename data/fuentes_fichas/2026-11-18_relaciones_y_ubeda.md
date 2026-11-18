# Fuentes: relaciones de la noche del 18-11-2026 y ficha de Úbeda

Comprobado de nuevo en la fuente primaria el 18-11-2026 entre las 00:30 y las 00:45 UTC.

## Recuento de `entity_relations` en prod

Fuente: consulta SQL a la BD de prod (`entity_relations`), 18-11-2026 00:34 UTC.

| estado | filas |
|---|---|
| verificada | 402 |
| pendiente | 62 |
| rechazada | 1 |

Cómo cuadra (misma consulta, por `created_at` y predicado):

| paso | verificadas |
|---|---|
| creadas antes del 17-11 23:00 UTC | 295 |
| 14 identidades nuevas (`sameAs`) | +14 |
| 89 relaciones T1 (`relaciones_auto.yaml`): 34 `memberOf`, 16 `alumniOf`, 14 `member`, 11 `foundingLocation`, 4 `birthPlace`, 4 `producer`, 2 `deathPlace`, 2 `founder`, 2 `location` | +89 |
| 2 `containedInPlace` del #141 (Torre Lucía y Casa de la Salud en Plasencia) | +2 |
| Úbeda: `sameAs` Q329984 y Sabina `birthPlace` → `place:ubeda` | +2 |
| **total** | **402** |

La fila 891 (el `birthPlace` literal «Úbeda» de Sabina, que cargó el #141) es la única `rechazada`:
la sustituye la relación con `place:ubeda`.

Las 62 pendientes son 61 conciertos sin dos medios de prensa con fecha y lugar, más el concierto de
Úbeda (fila 1316). El de Úbeda sí está verificado con dos medios, pero se dejó en `pendiente` hasta
desplegar el #146, porque el código de prod pinta la etiqueta cruda «event».

## Ficha de Úbeda: registro de afirmaciones

| ID | afirmación | dónde | fuente | evidencia | veredicto |
|---|---|---|---|---|---|
| A-01 | Robe tocó en Úbeda el 6 de julio de 2024 | cuerpo, title, description | Hora Jaén, 07-07-2024, https://www.horajaen.com/2024/07/07/robe-inaugura-festmuve-2024-en-ubeda-con-un-concierto-apoteosico/ | «La noche del sábado 6 de julio, el recinto ferial de Úbeda vibró al ritmo de Robe, quien dio el pistoletazo de salida a la programación de Festmuve 2024 con su gira «Ni santos ni inocentes».» | CONFIRMADA |
| A-02 | Lo mismo, con una segunda fuente independiente (fecha anunciada) | relación `event` | Vivir Ediciones, `datePublished` 2024-07-02T13:02:09+02:00, https://vivirediciones.es/?p=624827 (redirige a «Robe anuncia un segundo concierto en el Wizink…») | «…todavía pasará en julio por Córdoba (día 5), Úbeda (6), Gijón (12)…» | CONFIRMADA |
| A-03 | La gira es «Ni santos ni inocentes», la de *Se nos lleva el aire* | cuerpo | Hora Jaén (A-01) y Vivir Ediciones: «el tour con el que entre otras cosas promociona el disco ‘Se nos lleva el aire’» | literal en las dos | CONFIRMADA |
| A-04 | Sabina nació en Úbeda el 12-02-1949 | cuerpo | Wikidata Q363577 (P19 = Q329984, P569 = 1949-02-12) | propiedad P19 y P569 | CONFIRMADA |
| A-05 | Robe grabó «Calle Melancolía» para *Ni tan joven, ni tan viejo* (2019) | cuerpo | ficha de Sabina (`2026-11-17_lugares_sabina_libro.md`: Sony Music, MusicBrainz) | ver ese documento | CONFIRMADA |
| A-06 | Úbeda y Baeza son Patrimonio de la Humanidad desde el 03-07-2003 | cuerpo | Wikidata Q15831671 (P1435, calificador P580 = 2003-07-03; UNESCO 522) | propiedad P580 | CONFIRMADA |

Foto: la de Commons «Sacra Capilla del Salvador, en Úbeda» no acreditó procedencia
(`verify_provenance`) y la ficha va sin foto.

## JSON-LD

`audit_jsonld` contra prod, 18-11-2026 00:39 UTC, frente a la línea base de main (13-11):
- 393 URLs con 200;
- 1 fallo nuevo: `/personas/joaquin-sabina` cita `/lugares/ubeda#place` y la auditoría no veía la
  página, porque el sitemap estaba en caché. El sitemap se revalidó a las 00:41 UTC y ya trae
  `/lugares/ubeda`;
- 8 lugares sin canciones pierden adrede su `ItemList` vacío (#141): Barakaldo, Berriz, Bilbao,
  La Zubia, Madrid, Mérida, Muxika y Pamplona.

## Ficheros de trabajo

Los ficheros intermedios de la carga (candidatas, conciertos pendientes, ciudades sin ficha) vivían
en `/tmp/acum` del contenedor del api. Se copiaron a `/opt/robelyrics/data/_trabajo_relaciones_2026-11-18/`
(volumen montado) y a local, fuera de git: `conciertos_pendientes.yaml` sale de `conciertos.csv`,
que no se versiona porque el repo es público.
