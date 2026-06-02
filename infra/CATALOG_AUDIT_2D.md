# Auditoría de catálogo (2D) — obras faltantes

Fecha: 2026-06-01 (madrugada). Estado: **auditado, ingesta bloqueada por Genius**.

## Hallazgos

### 1. Falsos positivos del descubrimiento (NO faltan)
Las "obras" detectadas por `discover_entities` que parecían faltar **ya estaban
en el catálogo**, pero con títulos verbosos que el resolver no casaba:

| Mención corta | Título real en BD | Álbum |
|---|---|---|
| Jesucristo García | `Jesucristo García (Rock Transgresivo)` | Rock Transgresivo |
| Extremaydura | `Extremaydura (Rock Transgresivo)` | Rock Transgresivo |
| Bulerías de la sangre caliente | `Bulerías de la sangre caliente (...)` | Deltoya |
| Lucha Contigo | `Lucha Contigo (...)` | Deltoya |

→ **Arreglado** (commit `34ebaa9`): `entity_resolver._clean_title` añade al
índice del autolinker un alias sin el sufijo `(...)`/`[...]`, así que ahora
"Jesucristo García" enlaza a su canción. Ya desplegado y verificado.

### 2. Álbumes realmente ausentes
- **Pedrá** (1995, Extremoduro) — solo existe `La Pedrá (Fragmento) [En Directo]`
  en *Iros todos a tomar por culo*; el álbum completo no está.
- **Por la boca vive el pez** (2004, Extremoduro, directo doble) — ausente.

## Bloqueo: Genius tras Cloudflare
Al intentar `scripts.ingest --album-slug pedra ...` el 01/06, Genius responde
**403 con challenge de Cloudflare** (`cf-mitigated: challenge`). La librería
`lyricsgenius` no puede pasar el reto.

**No se usan herramientas de evasión antibot** (política del proyecto). Por eso
la ingesta de letras de estos dos álbumes **queda pendiente** hasta que Genius
vuelva a ser accesible (o se cambie de fuente de letras).

Se crearon y luego **se borraron** las filas de álbum vacías (habrían dejado
enlaces a 404 en `/discografia`). `discography.yaml` queda sin estas entradas.

## Resolución (2026-06-02)
Genius sigue bloqueado por Cloudflare. Se añadió un **ingest de respaldo**
(`scripts/ingest_lrclib.py`): tracklist de **MusicBrainz** + letras de
**LRCLIB**, sin scraping ni evasión.

- **Pedrá**: es un **single de 1995 (1 pista, la canción «Pedrá»)** — no un
  álbum. Ingestado vía LRCLIB (211 líneas), con YouTube + LRC sincronizado,
  contenido SEO de álbum y canción generados y **publicado**. ⚠️ MusicBrainz
  tiene además una release homónima recopilatoria mal etiquetada (25 pistas de
  varios discos); por eso el script filtra por **año exacto** (`--year 1995`).
- **Por la boca vive el pez (2004)**: no aparece en MusicBrainz y es un directo
  doble de versiones de temas de estudio ya publicados (anti-canibalización).
  **No se añade**; se retiró del catálogo. Pendiente de curación manual del
  tracklist o de que Genius vuelva.

## (Histórico) Cómo completar cuando Genius sea accesible
1. Reañadir a `data/discography.yaml`:
   - Extremoduro → `Pedrá` (1995, kind: studio, slug: `pedra`)
   - Extremoduro → `Por la boca vive el pez` (2004, kind: live, slug: `por-la-boca-vive-el-pez`)
2. `python -m scripts.seed_catalog`
3. `python -m scripts.ingest --album-slug pedra --album-slug por-la-boca-vive-el-pez`
4. `python -m scripts.embed_lyrics` (incremental)
5. `python -m scripts.match_youtube && python -m scripts.match_lrclib`
6. SEO público (cada página da 404 sin `seo_content` publicado — ver
   `web/app/[artist]/[album]/[song]/page.tsx:91`):
   - `python -m scripts.seo.generate_album_content --slug pedra`
   - `python -m scripts.seo.generate_song_content` para sus canciones
   - **Por la boca vive el pez es un directo**: ⚠️ anti-canibalización. Casi
     todas sus canciones son versiones en vivo de temas de estudio ya
     publicados. NO generar páginas de canción duplicadas que compitan con las
     de estudio; como mucho una página de álbum que enlace a las de estudio.
   - Revisión humana → `published=true`.
