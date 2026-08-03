"""La política de nombre deja de depender del ORM: trigger en la BD

«Robe Iniesta» no debe persistir NUNCA en contenido (a él no le gustaba). La
regla ya existía como listener de SQLAlchemy en `app/db/models.py`, pero un
listener de ORM solo corre cuando se escribe POR EL ORM: `pg_insert`, un
`update()` de Core, un script con SQL crudo o un `psql` a mano lo esquivan. Es
un agujero ya documentado en el proyecto («listener ORM muerto en generación,
pg_insert Core») y por él se coló «Robe Iniesta» en `artists.name`, que es lo
que pinta el breadcrumb, el <title> y el JSON-LD de cada disco de Robe.

Este trigger cierra el agujero en la capa que ningún camino de escritura puede
saltarse. El listener del ORM se queda como primera línea (falla antes y más
claro); esto es la red de abajo.

NO se aplica a las tablas que guardan texto AJENO —`interpretation_sources`,
`news_items`, `songs.lyrics_raw`, `news_source_runs`, `verification_records`—
porque reescribir el título de una fuente o un verso sería falsear el dato, que
es una regla más importante todavía. Ahí la forma vetada se cita, no se afirma.

Revision ID: robename2026_01
Revises: backcover2026_01
"""
from alembic import op

revision = "robename2026_01"
down_revision = "backcover2026_01"
branch_labels = None
depends_on = None

# tabla -> columnas nuestras (texto o jsonb) que publican contenido
PROTEGIDAS: dict[str, tuple[str, ...]] = {
    "artists": ("name",),
    "albums": ("title",),
    "bands": ("name", "bio_short", "bio_long", "related_note"),
    "persons": ("full_name", "stage_name", "bio_short", "bio_long"),
    "seo_content": ("body_md", "meta_title", "meta_description", "h1", "outline",
                    "secondary_keywords", "schema_jsonld", "entities", "target_keyword"),
    "posts": ("body_md", "title", "excerpt", "meta_title", "meta_description",
              "target_keyword", "entities"),
    "instagram_queue": ("caption", "title", "summary"),
    "consult_questions": ("citations",),
    "song_interpretations": ("payload",),
    "content_proposals": ("title", "angle", "body_md", "excerpt", "meta_title",
                          "meta_description", "target_keyword", "keywords", "entities"),
}

FUNCION = r"""
CREATE OR REPLACE FUNCTION enforce_robe_name() RETURNS trigger AS $$
DECLARE
  rec jsonb;
  col text;
  val jsonb;
  txt text;
  cambiado boolean := false;
BEGIN
  rec := to_jsonb(NEW);
  FOREACH col IN ARRAY TG_ARGV LOOP
    val := rec -> col;
    IF val IS NULL OR val = 'null'::jsonb THEN
      CONTINUE;
    END IF;
    txt := val::text;
    -- \y es frontera de palabra: no toca «Roberto Iniesta», que sí está permitida
    IF txt ~* '\yRobe\s+Iniesta\y' THEN
      rec := jsonb_set(rec, ARRAY[col],
                       regexp_replace(txt, '\yRobe\s+Iniesta\y', 'Robe', 'gi')::jsonb);
      cambiado := true;
    END IF;
  END LOOP;
  IF cambiado THEN
    NEW := jsonb_populate_record(NEW, rec);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def _columnas_reales(tabla: str, deseadas: tuple[str, ...]) -> list[str]:
    """Solo se protege lo que existe: el esquema ha ido cambiando y un trigger
    que nombra una columna inexistente revienta cada INSERT de esa tabla."""
    filas = op.get_bind().exec_driver_sql(
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema='public' AND table_name='{tabla}'").fetchall()
    existen = {f[0] for f in filas}
    return [c for c in deseadas if c in existen]


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(FUNCION)
    for tabla, columnas in PROTEGIDAS.items():
        reales = _columnas_reales(tabla, columnas)
        if not reales:
            continue
        args = ", ".join(f"'{c}'" for c in reales)
        conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS trg_robe_name ON {tabla}")
        conn.exec_driver_sql(
            f"CREATE TRIGGER trg_robe_name BEFORE INSERT OR UPDATE ON {tabla} "
            f"FOR EACH ROW EXECUTE FUNCTION enforce_robe_name({args})")


def downgrade() -> None:
    conn = op.get_bind()
    for tabla in PROTEGIDAS:
        conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS trg_robe_name ON {tabla}")
    conn.exec_driver_sql("DROP FUNCTION IF EXISTS enforce_robe_name()")
