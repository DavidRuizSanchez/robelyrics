"""Rehace las `bio_short` que quedaron cortadas a mitad de frase.

    python -m scripts.fix_bios_cortadas            # dry-run
    python -m scripts.fix_bios_cortadas --apply

`seed_persons` recortaba con `extract[:500]` a pelo y eso puede cambiar lo que
el texto DICE, no solo dónde acaba. Caso real del 03-08-2026: la bio de Uoho se
quedó en «…la banda Inconscientes, su etapa como vocalista principa» cuando la
frase entera era «…su etapa como vocalista principal EN SU BREVE PROYECTO
SOLISTA UOHO». Ese corte daba a entender que era el cantante de Inconscientes
—lo era Jon Calvo, de Memoria de Pez— y así salió publicado en Instagram.

La `bio_long` está completa y es la fuente para rehacerlas, así que no hace
falta volver a Wikipedia.
"""
import sys

sys.path.insert(0, "/app")
from sqlalchemy import select  # noqa: E402

from app.db.models import Person  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from scripts.seed_persons import _recorta_por_frase  # noqa: E402

CIERRES = (".", "!", "?", "…", "»", '"', "”")


def esta_cortada(bio: str | None) -> bool:
    """Una bio bien terminada cierra frase. Ojo con el espacio de ancho cero
    (U+200B) que Wikipedia deja tras las llamadas a referencia."""
    b = (bio or "").rstrip().rstrip("​").rstrip()
    return bool(b) and not b.endswith(CIERRES)


def main() -> int:
    aplicar = "--apply" in sys.argv
    db = SessionLocal()
    tocadas = 0
    for p in db.execute(select(Person)).scalars():
        if not esta_cortada(p.bio_short):
            continue
        fuente = p.bio_long or p.bio_short or ""
        nueva = _recorta_por_frase(fuente, 500)
        if not nueva or nueva == p.bio_short:
            print(f"  ✗ {p.slug}: sin fuente mejor, se deja como está")
            continue
        print(f"  {p.slug}")
        print(f"     antes: …{(p.bio_short or '')[-70:]}")
        print(f"     ahora: …{nueva[-70:]}")
        if aplicar:
            p.bio_short = nueva
            tocadas += 1
    if aplicar:
        db.commit()
        print(f"\nAPLICADO a {tocadas} biografías.")
    else:
        print("\ndry-run: no se ha escrito nada (--apply para aplicar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
