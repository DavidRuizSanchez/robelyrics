"""Mete en la meta description el VERSO que la gente está buscando.

    python -m scripts.seo.meta_verso            # dry-run
    python -m scripts.seo.meta_verso --apply

Hay páginas que rankean bien y no se llevan el clic. Medido el 03-08-2026:
`/robe/mayeutica/interludio` acumula **1.246 impresiones y 4 clics** (0,3%) y
`guerrero` un 0,8% **estando en la posición 3,1**, cuando en esa posición se
espera un 10%. No les falta posición: les falta que el resultado prometa lo que
el usuario busca.

Y lo que busca está en las propias queries: versos literales. «dejo las ventanas
sin cerrar» suma 246 impresiones en Interludio; «llegar al olimpo y robar el
fuego», 42 en Guerrero. Los títulos ya decían «letra», pero las descripciones
prometían análisis y crítica — otra cosa.

Cada verso de aquí está **verificado contra `songs.lyrics_raw`** antes de
escribirse. Uno que se buscaba mucho, «en cada batalla nunca me he rendido», no
aparece en la letra de Guerrero y por eso no está.

Solo toca metadatos; el cuerpo no se toca.
"""
import re
import sys
import unicodedata

sys.path.insert(0, "/app")
from sqlalchemy import select, update  # noqa: E402

from app.db.models import SeoContent, Song  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

# slug -> (target_keyword, title, description, verso_que_debe_estar_en_la_letra)
PLAN = {
    "interludio": (
        "Interludio Robe letra",
        "Interludio de Robe: letra y significado",
        "«Dejo las ventanas sin cerrar y la puerta abierta»: qué dice y qué "
        "significa «Interludio», la pieza que enlaza Mayéutica con La ley innata.",
        "dejo las ventanas sin cerrar y la puerta abierta",
    ),
    "guerrero": (
        "Guerrero Robe letra",
        "Guerrero de Robe: letra y significado",
        "«A ver si puedo llegar al Olimpo y robar el fuego»: la letra de "
        "«Guerrero» de Robe y qué cuenta, en Lo que aletea en nuestras cabezas.",
        "llegar al olimpo y robar el fuego",
    ),
    "puta-humanidad": (
        "Puta humanidad Robe letra",
        "Puta humanidad de Robe: letra y significado",
        "«Bienvenido al temporal»: la letra de «Puta humanidad» de Robe, su "
        "crítica con humor negro y qué lugar ocupa dentro de Destrozares.",
        "bienvenido al temporal",
    ),
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ\s]", " ", s)).strip()


def main() -> int:
    aplicar = "--apply" in sys.argv
    db = SessionLocal()
    cambios = 0
    for slug, (kw, title, desc, verso) in PLAN.items():
        song = db.execute(select(Song).where(Song.slug == slug)).scalar_one_or_none()
        if song is None:
            print(f"  ✗ no existe {slug}")
            continue
        # El verso citado TIENE que estar en la letra. Si no, no se escribe.
        if norm(verso) not in norm(song.lyrics_raw or ""):
            print(f"  ✗ ABORTA {slug}: «{verso}» no está en la letra")
            continue
        if len(title) > 60 or len(desc) > 155:
            print(f"  ✗ ABORTA {slug}: title {len(title)}c, desc {len(desc)}c")
            continue
        c = db.execute(select(SeoContent).where(
            SeoContent.entity_type == "song", SeoContent.entity_id == song.id
        )).scalar_one_or_none()
        if c is None:
            print(f"  ✗ sin ficha: {slug}")
            continue
        print(f"  {slug}  (verso verificado en la letra)")
        print(f"     title: {c.meta_title}")
        print(f"         →  {title}")
        print(f"     desc : {(c.meta_description or '')[:70]}…")
        print(f"         →  {desc[:70]}…")
        if aplicar:
            db.execute(update(SeoContent).where(
                SeoContent.entity_type == "song", SeoContent.entity_id == song.id
            ).values(target_keyword=kw, meta_title=title, meta_description=desc))
            cambios += 1
    if aplicar:
        db.commit()
        print(f"\nAPLICADO a {cambios} fichas.")
    else:
        print("\ndry-run: no se ha escrito nada (--apply para aplicar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
