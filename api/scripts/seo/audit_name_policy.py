"""¿Se ha colado «Robe Iniesta» en algún sitio? Barrido de TODA la BD.

La forma «Robe Iniesta» no debe persistir en contenido: a él no le gustaba. La
regla se aplica en tres capas y esta es la tercera:

  1. `text_sanitizer.enforce_name_policy` — la transformación canónica.
  2. Listener de ORM (`app/db/models.py`) + trigger `trg_robe_name` en la BD
     (migración `robename2026_01`). El trigger es el que ningún camino de
     escritura puede saltarse; el listener solo cubre lo que pasa por el ORM.
  3. Esto: un barrido que mira TODAS las columnas de texto y jsonb del esquema,
     incluidas las tablas que aún no tienen trigger, y avisa.

**Lo que NO se toca nunca**: las tablas que guardan texto AJENO. El título de
una entrevista, el nombre de un medio, una transcripción o un verso se CITAN
tal cual; reescribirlos sería falsear la fuente, que es una regla superior a la
del nombre. Esas tablas se cuentan aparte, como informativas.

    python -m scripts.seo.audit_name_policy            # informe
    python -m scripts.seo.audit_name_policy --fix      # corrige lo nuestro
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import text

from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PATRON_SQL = r"\yRobe\s+Iniesta\y"

# Texto de terceros: se cita, no se afirma. Nunca se reescribe.
AJENAS = {
    "interpretation_sources",   # transcripciones, entrevistas, anotaciones
    "news_items",               # titulares y medios externos
    "news_source_runs",         # nombres de feeds
    "verification_records",     # evidencia de verificación, es una prueba
    "youtube_ingest_queue",     # títulos de vídeo tal como los puso su autor
    "related_videos",           # ídem: «La Resistencia — Entrevista a Robe Iniesta»
    "songs",                    # lyrics_raw: los versos no se editan
}


def _columnas(db) -> list[tuple[str, str, str]]:
    filas = db.execute(text("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema='public'
          AND data_type IN ('text','character varying','jsonb')
        ORDER BY table_name, column_name""")).fetchall()
    return [(f.table_name, f.column_name, f.data_type) for f in filas]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true",
                    help="corrige las tablas propias (las ajenas nunca se tocan)")
    args = ap.parse_args()

    db = SessionLocal()
    nuestras: list[tuple[str, str, str, int]] = []
    ajenas: list[tuple[str, str, int]] = []

    for tabla, col, tipo in _columnas(db):
        expr = f'"{col}"::text' if tipo == "jsonb" else f'"{col}"'
        try:
            n = db.execute(text(f'SELECT count(*) FROM "{tabla}" WHERE {expr} ~* :p'),
                           {"p": PATRON_SQL}).scalar()
        except Exception:  # noqa: BLE001  (vistas, tablas sin permisos…)
            continue
        if not n:
            continue
        if tabla in AJENAS:
            ajenas.append((tabla, col, n))
        else:
            nuestras.append((tabla, col, tipo, n))

    total_nuestro = sum(x[3] for x in nuestras)
    logger.info("=== «Robe Iniesta» en CONTENIDO PROPIO: %d fila(s) ===", total_nuestro)
    for tabla, col, _tipo, n in nuestras:
        logger.info("  %-28s %-24s %d", tabla, col, n)
    if not nuestras:
        logger.info("  ✓ limpio")

    logger.info("")
    logger.info("=== en texto AJENO (se cita, NO se toca): %d fila(s) ===",
                sum(x[2] for x in ajenas))
    for tabla, col, n in ajenas:
        logger.info("  %-28s %-24s %d", tabla, col, n)

    if not args.fix:
        if nuestras:
            logger.info("\n(usa --fix para corregir el contenido propio)")
        raise SystemExit(1 if nuestras else 0)

    for tabla, col, tipo, _n in nuestras:
        if tipo == "jsonb":
            sql = (f'UPDATE "{tabla}" SET "{col}" = '
                   f"regexp_replace(\"{col}\"::text, :p, 'Robe', 'gi')::jsonb "
                   f'WHERE "{col}"::text ~* :p')
        else:
            sql = (f'UPDATE "{tabla}" SET "{col}" = '
                   f"regexp_replace(\"{col}\", :p, 'Robe', 'gi') "
                   f'WHERE "{col}" ~* :p')
        r = db.execute(text(sql), {"p": PATRON_SQL})
        logger.info("  ✓ %s.%s corregidas %d", tabla, col, r.rowcount)
    db.commit()
    logger.info("hecho")


if __name__ == "__main__":
    main()
