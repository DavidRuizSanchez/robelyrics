"""Buscar material para el corpus fuera de los canales que se vigilan.

`detect_uploads` solo barría @juancaraes y @tesonica, y de ellos ya estaba todo
dentro: «393 candidatos · 393 ya conocidos · 0 nuevos» (19 y 22-10-2026). Aquí
se BUSCA en YouTube por las voces de casa y por temas, y cada resultado pasa por
`corpus_trust.clasificar`, que decide si es A (voz), B (medio), C (fan) o nada.

Cuota: `search.list` cuesta 100 unidades y la diaria es de 10.000. Van como
mucho `TOPE_CONSULTAS` por pasada; las genéricas siempre y las de cada voz
ROTAN entre pasadas, para que en unas semanas se hayan hecho todas. Los
detalles (canal real, duración, descripción) se piden en lote con `videos.list`
(1 unidad cada 50). Un 403 corta la pasada sin fallar: es la cuota.

Uso (muestra para validar criterios, no escribe nada):
    python -m scripts.youtube.corpus_search --dry-run
    python -m scripts.youtube.corpus_search --dry-run --backfill --muestra 10
"""
from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import httpx

from app.services.corpus_trust import (
    MediosCorpus,
    Veredicto,
    Video,
    Voz,
    cargar_voces,
    clasificar,
)
from app.services.youtube_relevance import build_vocab, is_relevant
from scripts.match_youtube import parse_iso8601_duration

logger = logging.getLogger(__name__)

YT_API = "https://www.googleapis.com/youtube/v3"
TOPE_CONSULTAS = 25
RESULTADOS_POR_CONSULTA = 25
# Ventana de una pasada normal: el cron corre cada 3 días y se deja margen; lo
# repetido lo quita la deduplicación.
VENTANA_DIAS = 7

CONSULTAS_GENERICAS = (
    "Robe Iniesta entrevista",
    "Extremoduro entrevista",
    "Extremoduro documental",
    "especial Robe Iniesta",
    "Robe Iniesta rueda de prensa",
    "Extremoduro reportaje",
    "Robe Iniesta habla",
    "recordando a Robe Iniesta",
)


def consultas(voces: list[Voz], pasada: int, tope: int = TOPE_CONSULTAS) -> list[str]:
    """Las genéricas siempre; de las de cada voz, una ventana que rota por pasada.

    A un amigo se le busca junto a Robe o Extremoduro: «Leiva entrevista» a secas
    trae su carrera entera, y lo que interesa es lo que diga de Robe.
    """
    por_voz: list[str] = []
    for v in voces:
        if v.relacion == "robe":
            continue
        por_voz += [f"{v.nombre} Robe Iniesta", f"{v.nombre} Extremoduro"]
    hueco = max(tope - len(CONSULTAS_GENERICAS), 0)
    if not por_voz or not hueco:
        return list(CONSULTAS_GENERICAS)[:tope]
    inicio = (pasada * hueco) % len(por_voz)
    rota = (por_voz[inicio:] + por_voz[:inicio])[:hueco]
    return list(CONSULTAS_GENERICAS) + rota


class CuotaAgotada(Exception):
    pass


def buscar(client: httpx.Client, key: str, consulta: str,
           publicado_desde: datetime | None) -> list[str]:
    params = {
        "part": "snippet", "q": consulta, "type": "video",
        "maxResults": RESULTADOS_POR_CONSULTA, "relevanceLanguage": "es", "key": key,
    }
    if publicado_desde:
        params["publishedAfter"] = publicado_desde.strftime("%Y-%m-%dT%H:%M:%SZ")
    r = client.get(f"{YT_API}/search", params=params)
    if r.status_code == 403:
        raise CuotaAgotada(r.text[:200])
    if r.status_code != 200:
        logger.warning("search «%s» HTTP %s: %s", consulta, r.status_code, r.text[:140])
        return []
    return [it["id"]["videoId"] for it in r.json().get("items", [])
            if it.get("id", {}).get("videoId")]


def detalles(client: httpx.Client, key: str, ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        r = client.get(f"{YT_API}/videos", params={
            "part": "snippet,contentDetails", "id": ",".join(ids[i:i + 50]), "key": key,
        })
        if r.status_code == 403:
            raise CuotaAgotada(r.text[:200])
        if r.status_code != 200:
            logger.warning("videos.list HTTP %s: %s", r.status_code, r.text[:140])
            continue
        for it in r.json().get("items", []):
            sn, cd = it.get("snippet", {}), it.get("contentDetails", {})
            out[it["id"]] = {
                "title": sn.get("title") or "",
                "description": sn.get("description") or "",
                "channel_title": sn.get("channelTitle") or "",
                "channel_id": sn.get("channelId"),
                "published_at": sn.get("publishedAt"),
                "duration_s": parse_iso8601_duration(cd.get("duration")),
            }
    return out


def descubrir(db, key: str, *, backfill: bool = False, pasada: int | None = None,
              conocidos: set[str] | None = None) -> list[tuple[Video, Veredicto, dict]]:
    """Busca, pide detalles y clasifica. No escribe nada."""
    voces = cargar_voces(db)
    medios = MediosCorpus.desde_yaml()
    vocab = build_vocab(db)
    if pasada is None:
        pasada = datetime.now(UTC).toordinal() // 3
    desde = None if backfill else datetime.now(UTC) - timedelta(days=VENTANA_DIAS)
    conocidos = conocidos or set()

    encontrados: dict[str, str] = {}      # video_id → consulta que lo trajo
    with httpx.Client(timeout=30) as client:
        try:
            for q in consultas(voces, pasada):
                for vid in buscar(client, key, q, desde):
                    if vid not in conocidos:
                        encontrados.setdefault(vid, q)
            info = detalles(client, key, list(encontrados))
        except CuotaAgotada as e:
            logger.warning("cuota de YouTube agotada, se corta la pasada: %s", e)
            return []

    out = []
    for vid, d in info.items():
        relevante, _ = is_relevant(d["title"], d["description"], vocab=vocab,
                                   use_description=True)
        video = Video(video_id=vid, title=d["title"], channel_title=d["channel_title"],
                      channel_id=d["channel_id"], description=d["description"],
                      duration_s=d["duration_s"], relevante=relevante)
        out.append((video, clasificar(video, voces, medios),
                    {"consulta": encontrados[vid], "published_at": d["published_at"]}))
    return out


def _muestra(resultados, n: int) -> None:
    por_nivel: dict[str, list] = defaultdict(list)
    for video, ver, extra in resultados:
        por_nivel[ver.nivel].append((video, ver, extra))
    for nivel in ("A", "B", "C", "descartado"):
        filas = por_nivel.get(nivel, [])
        print(f"\n=== {nivel} · {len(filas)} vídeos ===")
        for video, ver, extra in filas[:n]:
            dur = f"{video.duration_s / 60:.0f} min" if video.duration_s else "?"
            print(f"- {video.title}")
            print(f"    canal: {video.channel_title} · {dur} · "
                  f"https://youtu.be/{video.video_id}")
            print(f"    kind: {ver.kind} · voces: {', '.join(ver.voces) or '—'}")
            print(f"    motivo: {' · '.join(ver.motivos)}")
            print(f"    encontrado con: «{extra['consulta']}»")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Solo enseña la muestra.")
    ap.add_argument("--backfill", action="store_true", help="Sin límite de fecha.")
    ap.add_argument("--muestra", type=int, default=10, help="Vídeos por nivel a enseñar.")
    ap.add_argument("--pasada", type=int, default=None, help="Fija la rotación de consultas.")
    args = ap.parse_args()
    if not args.dry_run:
        raise SystemExit("De momento solo --dry-run: la entrada en la cola llega tras validar.")

    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        raise SystemExit("Falta YOUTUBE_API_KEY")
    from app.db.session import SessionLocal
    from scripts.youtube.detect_uploads import _already_ingested_ids, _queued_ids

    with SessionLocal() as db:
        conocidos = _queued_ids(db) | _already_ingested_ids(db)
        resultados = descubrir(db, key, backfill=args.backfill, pasada=args.pasada,
                               conocidos=conocidos)
    _muestra(resultados, args.muestra)


if __name__ == "__main__":
    main()
