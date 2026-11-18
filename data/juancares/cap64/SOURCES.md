# SOURCES — Entidades del cap. 64 de Juancares («Plasencia y Robe»)

Extracción: 09-11-2026, 21:00-21:30 (hora local). Todo de **producción** (`ssh robelyrics`, solo lectura). La BD local está desfasada: no tiene este vídeo.

| Dato | Fuente | Query / fichero |
|---|---|---|
| Último vídeo de Juancares | `youtube_ingest_queue` id 111 (`cwUsXq54KvA`, publicado 07-11-2026, done 09-11-2026) e `interpretation_sources` id 1756 | `where author ilike '%juanca%' order by published_at desc` |
| Transcripción con tiempos | `source_segments where source_id=1756` (2.698 tramos, último a 12.555 s) | `segments.tsv`, `transcript.txt` |
| Cruce con la BD | `persons` (+ `band_memberships`), `artists`, `albums`, `songs`, `places` | `catalog.tsv`, `bd_personas.txt` |
| Canciones que suenan | `lines` (similitud trigram, `pg_trgm`) | `../frag.sql`; se dan por identificadas las de similitud ≥ 0,47 y se dice cuál es |
| Entidades | lectura completa de la transcripción, por bloques | `notas.md` → `../scripts/entidades.py` → `entidades_cap64.csv` / `.md` |

## Validación (09-11-2026, 21:27)
- **Minutos**: 360 de 360 comprueban que el nombre (o su grafía de Whisper) aparece en ese tramo o en los dos siguientes (`validacion_minutos.md`). La primera pasada dio 25 fallos: eran minutos de un hecho que no repetía el nombre; se cambiaron por el tramo donde sí se nombra.
- **Transcripción**: se volvió a descargar de prod y es byte a byte idéntica al volcado (`segments_revalidacion.tsv`).
- **Cifras**: 44 de 44 cifras del entregable están literales en la transcripción (`validacion_cifras.txt`).
- **Slugs de la BD**: los 41 slugs citados existen en prod (`bd_revalidacion.txt`). Los años de disco citados en las notas (1990, 1991, 1992, 1994, 1995, 2021) son los de `albums.year`.
- **Columna `tramos_que_casan`**: es un recuento grueso por texto, no un número de menciones. Los patrones cortos («hoy», «torre», «extremadura», «carlos»…) cuentan de más, y en «Extremoduro» Whisper confunde el grupo con la región.

## Qué NO se ha verificado
- Lo que cuenta el vídeo (fechas, cifras de público, anécdotas) es **lo que dicen el narrador y los entrevistados**. No se ha cotejado con fuentes externas: el alcance era vídeo + BD, sin web.
- Los nombres marcados como dudosos (Saldario, Ventura «Duerte», Rafael «Rever», «Hakara», Jorge «Armestad», «Misma», «Zosy», Juan Chu Iniesta, Nahum Iniesta…) se dejan tal como los escribe Whisper.
- Las identidades que se infieren van como [HIPÓTESIS]: que «Pepe Marinho» sea Mariño, que «José Luis Villa» sea Díaz, que «Luis Ba» sea Fanta, la alusión a Standby y el año del festival.
