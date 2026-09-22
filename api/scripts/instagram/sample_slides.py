"""Muestra el texto que escribiría el pipeline para un post, sin publicar nada.

Sirve para mirar con los ojos lo que ningún test puede juzgar: si las slides
dicen algo o son humo. Corre el camino REAL (material del corpus + redacción +
guardas), solo que imprime en vez de encolar.

Uso:
    python -m scripts.instagram.sample_slides --noticia app/tests/fixtures/caso_guardiola/noticia.txt
    python -m scripts.instagram.sample_slides --verso 1
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.db.models import Album, Artist, Line, Song
from app.db.session import SessionLocal
from app.services.instagram import carousel, material, newsroom

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _pinta(topic: dict) -> None:
    print("\n" + "=" * 72)
    print(f"TITULAR   {topic.get('headline', '')}")
    print(f"COMENTARIO\n{topic.get('caption_body', '')}")
    print("\nSLIDES")
    for i, s in enumerate(topic.get("slides") or [], start=1):
        print(f"  {i}. [{s.get('kicker', '')}] {s.get('text', '')}")
    print(f"\nCIERRE    {topic.get('cierre', '')}")
    specs = carousel.plan(topic, topic.get("content_type", "news"))
    print(f"\nCARRUSEL  {len(specs) if specs else 0} tarjetas "
          f"({[s['layout'] for s in specs] if specs else 'foto única'})")
    if topic.get("avisos"):
        print(f"AVISOS    {topic['avisos']}")
    print("=" * 72)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--noticia", help="fichero con el cuerpo del artículo")
    ap.add_argument("--titulo", default="")
    ap.add_argument("--verso", type=int, help="id de una línea para un post de verso")
    args = ap.parse_args()

    with SessionLocal() as db:
        if args.verso:
            row = db.execute(
                select(Line.text, Song.title, Album.title, Album.year, Artist.name)
                .select_from(Line)
                .join(Song, Line.song_id == Song.id)
                .join(Album, Song.album_id == Album.id)
                .join(Artist, Album.artist_id == Artist.id)
                .where(Line.id == args.verso)
            ).first()
            if not row:
                raise SystemExit(f"No existe la línea {args.verso}")
            verso, song, album, year, artist = row
            topic = {
                "title": verso, "caption_body": verso, "summary": verso,
                "content_type": "quote", "corpus": {
                    "song": song, "album": album, "year": year, "artist": artist,
                },
                "tone": "neutral",
            }
            topic["texto_base"] = verso
            mat = material.reunir(db, topic)
            print(f"\n[material del corpus: {len(mat.prompt)} caracteres]")
            if not mat:
                raise SystemExit("Sin material: el post saldría con el texto de siempre.")
            topic["material_corpus"] = mat.prompt
            topic["avisos"] = newsroom.escribir(
                db, topic, [], material=f"{verso}\n\n{mat.prompt}", verificar_rel=False
            )
            _pinta(topic)
            return

        if not args.noticia:
            raise SystemExit("Hace falta --noticia o --verso")
        with open(args.noticia, encoding="utf-8") as fh:
            cuerpo = fh.read()
        titulo = args.titulo or cuerpo.strip().splitlines()[0][:150]
        topic = {
            "title": titulo, "summary": "", "category": "Actualidad",
            "material": cuerpo, "content_type": "news", "corpus": {},
            "tone": "neutral",
        }
        entidades = newsroom.resolver_entidades(db, topic)
        print(f"[entidades: {[(e.mention.surface, e.label, e.status) for e in entidades]}]")
        mat = material.reunir(db, topic, entidades=entidades)
        topic["material_corpus"] = mat.prompt
        print(f"[material del corpus: {len(mat.prompt)} caracteres "
              f"· verificable: {len(mat.verificable)}]")
        verif = f"{cuerpo}\n\n{mat.verificable}".strip()
        topic["avisos"] = newsroom.escribir(
            db, topic, entidades, material=verif, material_verificable=verif
        )
        _pinta(topic)


if __name__ == "__main__":
    main()
