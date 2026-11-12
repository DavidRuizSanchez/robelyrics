"""Títulos de canción y de disco con mayúsculas a la española (David, 12-11-2026).

Aplica `data/titulos_canciones.yaml`, que es la única fuente: revisado a mano y
aprobado por David. Para cada entrada:

1. Cambia `songs.title` / `albums.title` si la BD sigue diciendo `antes` (si ya
   dice `titulo`, no hay nada que hacer; si dice otra cosa, se avisa y no se toca).
2. Sustituye la grafía vieja por la nueva en el texto publicado (`seo_content` y
   `posts`: cuerpo, title, description, h1, excerpt, JSON-LD) con
   `reemplazar_titulo`, que solo toca el título citado, no una frase que coincida.
   Guarda `content_revisions` (reason «títulos a la española») antes de escribir.
3. Actualiza `song_title` en los payloads de Qdrant (`lines_v1`, `lyrics_full_v1`),
   que es lo que pinta el buscador.

    python -m scripts.normalizar_titulos                 (ensayo)
    python -m scripts.normalizar_titulos --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REASON = "títulos a la española (normalizar_titulos 12-11-2026)"
_CANDIDATOS = (Path("/app/data/titulos_canciones.yaml"),
               Path(__file__).resolve().parents[2] / "data" / "titulos_canciones.yaml")
# Un título que es también una frase o un nombre de la casa solo se cambia cuando
# va citado («…», *…*, enlace): «Entre Interiores» es el nombre de la web.
_SOLO_CITADO = {"Entre Interiores"}
_ABRE = r"(?<=[«“\"'*_\[])"
_CIERRA = r"(?=[»”\"'*_\]])"


def _distintivo(antes: str) -> bool:
    """Dos o más mayúsculas fuera de la primera palabra: ese string solo puede ser
    el título («Ábreme el Pecho y Registra»), nunca una frase normal."""
    palabras = re.findall(r"[^\W\d_]+", antes)
    return sum(1 for p in palabras[1:] if p[:1].isupper()) >= 2


def reemplazar_titulo(texto: str, antes: str, despues: str) -> str:
    """El título viejo por el nuevo. Si es distintivo, en cualquier sitio; si no
    («Tu Corazón», «La Carrera»), solo citado o como texto de un enlace."""
    if not texto or antes == despues or antes not in texto:
        return texto
    if texto == antes:  # el campo ES el título (un h1)
        return despues
    esc = re.escape(antes)
    if _distintivo(antes) and antes not in _SOLO_CITADO:
        return re.sub(r"(?<![\w])" + esc + r"(?![\w])", despues, texto)
    return re.sub(_ABRE + esc + _CIERRA, despues, texto)


def _cargar() -> dict:
    for p in _CANDIDATOS:
        if p.exists():
            return yaml.safe_load(p.read_text()) or {}
    raise SystemExit("no encuentro data/titulos_canciones.yaml")


def _campos_texto(kind: str) -> tuple[str, ...]:
    if kind == "post":
        return ("body_md", "title", "excerpt", "meta_title", "meta_description")
    return ("body_md", "meta_title", "meta_description", "h1", "schema_jsonld", "entities")


def main() -> None:
    from app.db.models import Album, Artist, ContentRevision, Post, SeoContent, Song
    from app.db.session import SessionLocal
    from app.services.link_policy import rutas_de_nodos

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sin-qdrant", action="store_true", help="no tocar los payloads")
    args = ap.parse_args()
    datos = _cargar()

    informe = {"canciones": 0, "discos": 0, "ya_estaban": 0, "no_coinciden": [],
               "paginas": 0, "aplicado": args.apply}
    pares: list[tuple[str, str]] = []
    qdrant_titulos: dict[int, str] = {}
    with SessionLocal() as db:
        artistas = {a.slug: a.id for a in db.query(Artist).all()}
        for e in datos.get("discos", []):
            alb = db.query(Album).filter_by(artist_id=artistas.get(e["artist"]),
                                            slug=e["album"]).one_or_none()
            if alb is None or alb.title not in (e["antes"], e["titulo"]):
                informe["no_coinciden"].append(f"disco {e['album']}: {alb.title if alb else 'no existe'}")
                continue
            pares.append((e["antes"], e["titulo"]))
            if alb.title == e["titulo"]:
                informe["ya_estaban"] += 1
                continue
            informe["discos"] += 1
            if args.apply:
                alb.title = e["titulo"]
        for e in datos.get("canciones", []):
            song = (db.query(Song).join(Album, Song.album_id == Album.id)
                    .filter(Album.artist_id == artistas.get(e["artist"]),
                            Album.slug == e["album"], Song.slug == e["slug"]).one_or_none())
            if song is None or song.title not in (e["antes"], e["titulo"]):
                informe["no_coinciden"].append(f"{e['album']}/{e['slug']}: {song.title if song else 'no existe'}")
                continue
            pares.append((e["antes"], e["titulo"]))
            qdrant_titulos[song.id] = e["titulo"]
            if song.title == e["titulo"]:
                informe["ya_estaban"] += 1
                continue
            informe["canciones"] += 1
            if args.apply:
                song.title = e["titulo"]
        if args.apply:
            db.commit()

        # Los más largos primero: «La Hoguera (Rock Transgresivo)» antes que «La Hoguera».
        pares.sort(key=lambda p: -len(p[0]))
        muestra, tocadas = [], []
        rutas = rutas_de_nodos(db)  # la ruta va en la revisión: el seguimiento la lee
        filas = [("post", p) for p in db.query(Post).all()]
        filas += [("seo_content", s) for s in db.query(SeoContent).all()]
        for kind, row in filas:
            cambios = {}
            for f in _campos_texto(kind):
                v = getattr(row, f, None)
                raw = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if v else None
                if not raw:
                    continue
                nuevo = raw
                for antes, despues in pares:
                    nuevo = reemplazar_titulo(nuevo, antes, despues)
                if nuevo != raw:
                    cambios[f] = nuevo if isinstance(v, str) else json.loads(nuevo)
            if not cambios:
                continue
            informe["paginas"] += 1
            if len(muestra) < 6 and "meta_title" in cambios:
                muestra.append({"pagina": f"{kind}:{row.slug}", "antes": row.meta_title,
                                "despues": cambios["meta_title"]})
            if args.apply:
                db.add(ContentRevision(
                    target_kind=kind, target_id=row.id,
                    path=(f"/blog/{row.slug}" if kind == "post"
                          else rutas.get((row.entity_type, row.entity_id), "")),
                    body_md=row.body_md, meta_title=row.meta_title,
                    meta_description=row.meta_description,
                    h1=getattr(row, "h1", None) if kind == "seo_content" else row.title,
                    reason=REASON,
                ))
                for f, nuevo in cambios.items():
                    setattr(row, f, nuevo)
                db.commit()
                ruta = (f"/blog/{row.slug}" if kind == "post"
                        else rutas.get((row.entity_type, row.entity_id)))
                if ruta:
                    tocadas.append(ruta)

    if args.apply and not args.sin_qdrant and qdrant_titulos:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        from app.services.qdrant_client import get_qdrant

        q = get_qdrant()
        for coleccion in ("lines_v1", "lyrics_full_v1"):
            for song_id, titulo in qdrant_titulos.items():
                q.set_payload(coleccion, payload={"song_title": titulo},
                              points=Filter(must=[FieldCondition(key="song_id",
                                                                 match=MatchValue(value=song_id))]))
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    for m in muestra:
        print(json.dumps(m, ensure_ascii=False))
    if args.apply and tocadas:
        from app.services.publishing import revalidate_paths

        # Rutas concretas: vaciar la caché entera dejó las discografías en 404
        # el 12-11-2026. Las fichas de canción que solo cambian de H1 se ven al
        # caducar la caché (revalidate = 3600).
        revalidate_paths(sorted(set(tocadas)) + ["/blog"])


if __name__ == "__main__":
    main()
