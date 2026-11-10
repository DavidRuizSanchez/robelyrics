# Entidades del cap. 64 de Juancares («Plasencia y Robe»)

Vídeo: «¡ESTRENO! PLASENCIA Y ROBE. CAPÍTULO 64 DE LA HISTORIA DE EXTREMODURO»
(`cwUsXq54KvA`, publicado el 07-11-2026, 3 h 29 min). En prod es
`interpretation_sources.id = 1756`, con 2.698 `source_segments`.

Extracción del 09-11-2026: **208 entidades, 41 con ficha en la BD**. El alcance era
lo que dice el vídeo cruzado con la BD de prod, sin web. Lo que cuenta el vídeo es
material AJENO: orienta, no se afirma sin corroborar (ver «La voz es nuestra» en
`CLAUDE.md`).

## Ficheros

| Fichero | Qué es |
|---|---|
| `entidades_cap64.md` | El informe: cada entidad con lo que dice el vídeo, minutos y cruce con la BD |
| `entidades_cap64.csv` | Lo mismo en tabla (una fila por entidad, `E-001`…`E-208`) |
| `SOURCES.md` | Fuentes, queries y validación del informe |
| `notas.md` | Notas de lectura de la transcripción, por bloques |
| `catalog.tsv`, `bd_personas.txt` | Volcado del catálogo de prod usado para el cruce |
| `bd_revalidacion.txt` | Revalidación de los 41 slugs citados contra prod |
| `validacion_minutos.md`, `validacion_cifras.txt` | Validación de minutos (360/360) y cifras (44/44) |
| `scripts/entidades.py` | Las entidades, a mano, tras leer la transcripción entera |
| `scripts/build.py` | Genera el CSV y el MD y valida cada minuto contra `segments.tsv` |
| `scripts/frag.sql` | Identificación de canciones por similitud trigram contra `lines` |
| `transcript.txt`, `segments*.tsv` | **No versionados** (`.gitignore`): copia de la transcripción de prod |

## Regenerar

```bash
# 1. Volcar la transcripción de prod (solo lectura)
Q='select idx, round(start_s::numeric,1), round(end_s::numeric,1), text from source_segments where source_id=1756 order by idx'
ssh robelyrics "docker exec robelyrics-postgres sh -c 'psql -U \$POSTGRES_USER -d \$POSTGRES_DB -At -F \"\$(printf \"\\t\")\" -c \"$Q\"'" \
  > data/juancares/cap64/segments.tsv
# 2. Generar CSV + MD y validar minutos
python data/juancares/cap64/scripts/build.py data/juancares/cap64
```

Comprobado el 10-11-2026: devuelve los 2.698 tramos y coincide con el volcado del
09-11 salvo en un tramo. En el 2546, prod dice hoy «…ha muerto a los 63 años, Robe,»
donde el 09-11 decía «Robe Iniesta». Es la política de nombre de la BD (nunca «Robe
Iniesta») aplicada después del volcado.

## Trampas medidas

- **Solo prod**: la BD local acaba en junio de 2026 y no tiene el vídeo.
- Whisper escribe «Extremadura» por «Extremoduro» y destroza nombres propios
  (Saldario, «Hakara», «Balcorchero»…): se dejan tal cual, marcados.
- Un minuto citado tiene que ser el del NOMBRE, no el del hecho: la primera pasada
  falló en 25.
- No se completan nombres que el vídeo no dice.

## Siguiente

`analisis_personas/`: criba y propuesta para dar de alta personas
(plan del 10-11-2026). Todavía no se crea nada.
