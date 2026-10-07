# Material de la campaña — índice para revisión

Todo lo producido hasta el 07-10-2026. Lo que está **publicado solo en local** no
existe todavía en entreinteriores.com.

## 1. Para mirar ahora

| Qué | Dónde | Estado |
|---|---|---|
| **El post de la ola 1** | `http://localhost:3001/blog/canciones-extremoduro-sin-registro-en-directo` | publicado **solo en local** |
| **Boceto de la infografía** (estudio completo) | `https://claude.ai/artifact/U2EcKkp5ueVsbj2NueuzpG` | borrador privado |
| **Carrusel de Instagram** (5 slides, 1080×1350) | `<scratchpad>/ig/slide1..5.png` | **sin publicar** |
| **Caption de Instagram** | `<scratchpad>/ig/caption.txt` | sin publicar · 977 car. · 0 moldes |

## 2. La trazabilidad

| Documento | Qué contiene |
|---|---|
| `data/estudio/SOURCES.md` | **El ledger.** 30 cifras validadas contra la fuente, el registro de afirmaciones V-01…V-09 y lo que NO se puede afirmar. Si una cifra no está aquí, no se publica. |
| `data/estudio/FUENTES_CONCIERTOS.md` | Research de fuentes para contrastar conciertos: Wikipedia, laleydeextremoduro, Rock Circus, nuestro corpus. Y por qué Songkick no sirve. |

## 3. Los datos

En el scratchpad, **no versionados a propósito**: llevan dentro cifras de setlist.fm y
sus términos no permiten retener copias. Se regeneran con dos comandos (abajo).

| Fichero | Filas | Qué es |
|---|---|---|
| `nunca_tocadas.csv` | 11 | Las once, con disco, año, ruta y demanda de búsqueda |
| `repertorio_unificado.csv` | 137 | Cada título con sus toques por formación y su índice |
| `deuda_setlist.csv` | 22 | Lo que se busca frente a lo que sonaba |
| `versos_mas_repetidos.csv` | 25 | El ranking de versos del catálogo |
| `conciertos.csv` | 591 | Fecha, ciudad, recinto y país de cada concierto |
| `geografia.json` | — | Ciudades, recintos, países y cobertura |
| `estudio.json` | — | Todo lo calculado sobre nuestro catálogo |

## 4. El código

| Script | Qué hace |
|---|---|
| `api/scripts/pr/setlist_parse.py` | Parseo determinista de setlist.fm (no lo lee un modelo) |
| `api/scripts/pr/fetch_setlist_index.py` | Descarga por HTTP; falla si el WAF corta, no escribe vacío |
| `api/scripts/pr/crawl_setlist_browser.py` | Navegador real: años, giras y el índice de conciertos |
| `api/scripts/pr/build_study_dataset.py` | Cruce con nuestro catálogo. Solo lectura de la BD |
| `api/scripts/pr/analyze_geography.py` | Ciudades y recintos, con los tres saneados |
| `api/scripts/pr/mine_authorship.py` | Red de arrastre de candidatos de autoría (da ruido: es shortlist, no respuesta) |
| `api/scripts/blog/seed_estudio_post.py` | El post, idempotente, pasando por las guardas |

### Regenerar los datos

```bash
# navegador real (local, 3,5 s entre peticiones)
cd api && PYTHONPATH=. python3 -m scripts.pr.crawl_setlist_browser --out DIR --what anios,giras,conciertos
PYTHONPATH=. python3 -m scripts.pr.analyze_geography --browser DIR/setlist_browser.json --out DIR
# cruce con nuestro catálogo
docker compose exec api python -m scripts.pr.build_study_dataset --out /tmp/estudio --setlist /tmp/estudio/setlist_stats.json
```

## 5. Lo que falta antes de que esto sea público

1. **Desplegar**: mergear la rama a `main`, rsync a `/opt/robelyrics/`, **rebuild del
   contenedor `web`** (sin él la tabla sale sin estilar y los enlaces a setlist.fm
   irían con `nofollow`, que incumple sus términos) y correr el seed en el servidor.
2. **Aprobar el carrusel** y encolarlo por `blog_post_id` para que pase por
   `caption_guard` y `tono_guard`.
3. **Press kit**: PNG de prensa, resumen de 150 palabras, declaraciones y el CSV
   bajo CC BY.
4. **Las 6 atribuciones retenidas** van como `[HIPÓTESIS]` o fuera (ver V-09).
