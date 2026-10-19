"""Vectoriza un resumen de cada página publicada en la colección `pages_v1`.

Es la señal semántica de `content_placement`: dada una idea de post, qué página
del sitio trata ya ese tema. Antes no existía ninguna búsqueda por página —las
colecciones eran de versos, corpus e interpretaciones—, así que nada podía decir
que «el género musical de Extremoduro» ya es una sección de `/extremoduro`.

Por página se embebe: título, description, los headings y el arranque del cuerpo.
Es un resumen a propósito: el cuerpo entero diluye el vector y una ficha larga se
parecería a todo.

Incremental: el payload guarda el hash del texto y solo se re-embebe lo que
cambió; lo despublicado se borra. Corre en el cron nocturno.

Uso: python -m scripts.seo.embed_pages [--dry-run] [--full]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import uuid

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointIdsList, PointStruct, VectorParams

from app.config import get_settings
from app.db.models import Post, SeoContent
from app.services.content_placement import PAGES_COLLECTION, PAGINAS
from app.services.url_resolver import DbCatalog
from scripts.research.common import get_session, log
from scripts.research.embed_interpretations import embed_batch

EMBED_DIM = 3072
ARRANQUE = 1500


def _point_id(path: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"page:{path}"))


def resumen(title: str | None, description: str | None, body_md: str | None) -> str:
    body = body_md or ""
    heads = re.findall(r"^#{2,3}\s+(.+)$", body, re.M)
    arranque = re.sub(r"\s+", " ", re.sub(r"^#.*$", "", body, flags=re.M))[:ARRANQUE]
    partes = [title or "", description or "", " · ".join(heads), arranque]
    return "\n".join(p.strip() for p in partes if p and p.strip())


def paginas(db) -> list[dict]:
    # Un solo catálogo: `canonical_path_for` monta uno por llamada, y aquí son
    # cientos de fichas en el cron de las 03:30.
    catalogo = DbCatalog(db)
    out = []
    for sc in db.query(SeoContent).filter(SeoContent.published.is_(True)).all():
        if not (sc.body_md or "").strip():
            continue
        if sc.entity_type == "page":
            path = (PAGINAS.get(sc.entity_id) or {}).get("path")
        else:
            path = catalogo.canonical_path(sc.entity_type, sc.entity_id)
        if not path:
            continue
        out.append({"path": path, "kind": "ficha", "target": f"ficha:{sc.id}",
                    "text": resumen(sc.meta_title or sc.h1, sc.meta_description, sc.body_md)})
    for p in db.query(Post).filter(Post.status == "published").all():
        out.append({"path": f"/blog/{p.slug}", "kind": "post", "target": f"post:{p.id}",
                    "text": resumen(p.meta_title or p.title, p.meta_description or p.excerpt,
                                    p.body_md)})
    for o in out:
        o["hash"] = hashlib.sha1(o["text"].encode("utf-8")).hexdigest()
    return out


def _existentes(qdrant: QdrantClient) -> dict[str, str]:
    """{point_id: hash} de lo que ya hay en la colección."""
    vistos: dict[str, str] = {}
    offset = None
    while True:
        pts, offset = qdrant.scroll(collection_name=PAGES_COLLECTION, limit=256,
                                    offset=offset, with_payload=["hash"],
                                    with_vectors=False)
        for p in pts:
            vistos[str(p.id)] = (p.payload or {}).get("hash") or ""
        if offset is None:
            return vistos


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full", action="store_true", help="re-embeber todo")
    args = parser.parse_args()

    settings = get_settings()
    qdrant = QdrantClient(url=settings.qdrant_url)
    if PAGES_COLLECTION not in {c.name for c in qdrant.get_collections().collections}:
        if args.dry_run:
            log(f"(dry-run) habría que crear {PAGES_COLLECTION}")
        else:
            qdrant.create_collection(
                collection_name=PAGES_COLLECTION,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE))
            log(f"colección Qdrant creada: {PAGES_COLLECTION}", "ok")

    with get_session() as db:
        todas = paginas(db)
    try:
        hay = _existentes(qdrant)
    except Exception:  # noqa: BLE001
        hay = {}
    vivas = {_point_id(p["path"]): p for p in todas}
    pendientes = [p for pid, p in vivas.items() if args.full or hay.get(pid) != p["hash"]]
    sobran = [pid for pid in hay if pid not in vivas]
    log(f"{len(todas)} páginas publicadas · {len(pendientes)} por embeber · "
        f"{len(sobran)} despublicadas que se borran")
    if args.dry_run:
        return

    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    openai = OpenAI(api_key=settings.openai_api_key)
    for i in range(0, len(pendientes), 64):
        lote = pendientes[i:i + 64]
        vecs = embed_batch(openai, [p["text"] for p in lote])
        qdrant.upsert(collection_name=PAGES_COLLECTION, points=[
            PointStruct(id=_point_id(p["path"]), vector=v,
                        payload={"path": p["path"], "kind": p["kind"], "target": p["target"],
                                 "hash": p["hash"]})
            for p, v in zip(lote, vecs, strict=True)
        ])
    if sobran:
        qdrant.delete(collection_name=PAGES_COLLECTION,
                      points_selector=PointIdsList(points=sobran))
    log(f"{PAGES_COLLECTION}: {len(pendientes)} embebidas, {len(sobran)} borradas", "ok")


if __name__ == "__main__":
    main()
