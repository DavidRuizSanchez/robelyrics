"""Reconstruye el setlist de un concierto a partir de su AUDIO (vídeo de YouTube).

Corre en el contenedor api LOCAL (yt-dlp desde una IP de servidor recibe bloqueo):

    docker compose exec api python -m scripts.pr.audio_setlist --id k2Z0k1-S_NY \
        --artista Extremoduro --concierto "1992-11-14 · Sala Escena, La Zubia"

Mismas piezas que el pipeline de clips (`scripts/instagram/transcribir_concierto.py` y
`app/services/instagram/momentos.py`), con dos diferencias:

- Baja el concierto ENTERO y lo trocea en tramos de 20 min para Whisper (límite de 25 MB),
  sumando el offset de cada tramo: sin eso, los tiempos del segundo tramo mienten.
- NO escribe en la BD. La transcripción de un directo está garbleada y no debe entrar al
  corpus; aquí solo sirve para saber QUÉ canción suena y CUÁNDO.

Una canción se da por identificada solo si al menos dos tramos de voz casan con versos
suyos, o uno con parecido muy alto: un fragmento corto casa con cualquier cosa (medido:
«¡Vamos Manolo!» salía como verso a 0,80). Cada canción lleva su minuto, que es la evidencia:
se comprueba escuchando.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import tempfile
import unicodedata
from datetime import datetime

from sqlalchemy import text as sqltext

from app.db.session import SessionLocal
from app.services.instagram import momentos, video_clips

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("audio_setlist")

TRAMO_S = 20 * 60
COSTE_POR_MINUTO = 0.006
SALIDA = "/app/.audio_setlists"
CONFIANZA_SOLA = 0.9
# Calibrado contra setlists conocidos (Festimad 1997 con la lista de Radio 3 y Plasencia 1991
# con el tracklist de su vídeo): por debajo de 0,8 de parecido máximo salían falsos positivos
# («Sin dios ni amo» a 0,71 donde sonaba «De acero»; «Desidia» a 0,75).
MEJOR_MINIMO = 0.8


def descargar(url: str, destino: str) -> None:
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmp:
        op = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": os.path.join(tmp, "a.%(ext)s"),
            "quiet": True, "noprogress": True, "no_warnings": True,
            **video_clips.runtime_js_para_ytdlp(),
        }
        with yt_dlp.YoutubeDL(op) as ydl:
            ydl.extract_info(url, download=True)
        crudo = max((os.path.join(tmp, f) for f in os.listdir(tmp)), key=os.path.getsize)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", crudo, "-ar", "16000", "-ac", "1",
                        "-q:a", "9", destino], check=True)


def duracion(audio: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "csv=p=0", audio], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def transcribir(audio: str, client) -> list[dict]:
    total, segmentos = duracion(audio), []
    with tempfile.TemporaryDirectory() as tmp:
        inicio = 0.0
        while inicio < total:
            tramo = os.path.join(tmp, f"t{int(inicio)}.mp3")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(inicio), "-t", str(TRAMO_S),
                            "-i", audio, "-c", "copy", tramo], check=True)
            with open(tramo, "rb") as fh:
                resp = client.audio.transcriptions.create(
                    model="whisper-1", file=fh, language="es", response_format="verbose_json",
                    timestamp_granularities=["segment"])
            for s in getattr(resp, "segments", None) or []:
                segmentos.append({"start_s": s.start + inicio, "end_s": s.end + inicio,
                                  "text": s.text,
                                  "no_speech_prob": getattr(s, "no_speech_prob", None)})
            logger.info("tramo %d-%d s: %d segmentos", inicio, min(total, inicio + TRAMO_S),
                        len(segmentos))
            inicio += TRAMO_S
    return segmentos


def canonico(titulo: str) -> str:
    """«Jesucristo García (En Directo)» y «… (Rock Transgresivo)» son la misma canción: el
    catálogo tiene filas por grabación, no por composición."""
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", titulo or "")
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9 ]+", " ", t).split()
    if t and t[0] in ("la", "el", "los", "las"):
        t = t[1:]
    return " ".join(t)


def anios_de_estreno(db) -> dict[str, int]:
    """Año más antiguo en que se publicó cada composición (por título canónico)."""
    anios: dict[str, int] = {}
    for titulo, anio in db.execute(sqltext(
            "select s.title, a.year from songs s join albums a on a.id = s.album_id "
            "where a.year is not null")).all():
        k = canonico(titulo)
        anios[k] = min(anio, anios.get(k, anio))
    return anios


def setlist(segmentos: list[dict], catalogo, anios: dict[str, int],
            anio_concierto: int | None) -> tuple[list[dict], list[str]]:
    """Bloques de canción con su minuto de inicio.

    1. Se identifica cada tramo y se descarta lo que se publicó DESPUÉS del concierto: hay
       versos que se repiten entre canciones (medido: Festimad 1997 daba «Coda flamenca», que
       es de 2008).
    2. Se tiran los aciertos aislados: un acierto sin otro de la misma canción a ±120 s es
       ruido (un verso parecido), y además partía los bloques de la canción de verdad.
    3. Se agrupa por canción canónica con huecos de hasta 120 s.
    """
    descartes, aciertos = [], []
    for s in segmentos:
        cancion, verso, conf = momentos.identificar(s["text"], catalogo)
        if not cancion:
            continue
        k = canonico(cancion)
        estreno = anios.get(k)
        # Un grupo estrena en directo antes de grabar: el disco del año siguiente se admite,
        # marcado. Lo de más allá es otro verso parecido, no la canción.
        if anio_concierto and estreno and estreno > anio_concierto + 1:
            descartes.append(f"{mmss(s['start_s'])} «{cancion}» (estreno {estreno}, posterior)")
            continue
        aviso = (f"publicada en {estreno}: ¿aún inédita?"
                 if anio_concierto and estreno and estreno > anio_concierto else "")
        aciertos.append({"k": k, "cancion": cancion, "t0": s["start_s"], "t1": s["end_s"],
                         "conf": conf, "verso": verso, "oido": s["text"].strip(), "aviso": aviso})
    firmes = [a for a in aciertos
              if a["conf"] >= CONFIANZA_SOLA and any(
                  b is not a and b["k"] == a["k"] and abs(b["t0"] - a["t0"]) <= 120 for b in aciertos)
              or sum(1 for b in aciertos if b["k"] == a["k"] and abs(b["t0"] - a["t0"]) <= 120) >= 2]
    bloques: list[dict] = []
    for a in firmes:
        ultimo = next((b for b in reversed(bloques) if b["k"] == a["k"]), None)
        if ultimo and a["t0"] - ultimo["fin_s"] <= 120 and ultimo is bloques[-1]:
            ultimo["fin_s"], ultimo["aciertos"] = a["t1"], ultimo["aciertos"] + 1
            ultimo["mejor"] = max(ultimo["mejor"], a["conf"])
            continue
        bloques.append({"k": a["k"], "cancion": a["cancion"], "inicio_s": a["t0"], "fin_s": a["t1"],
                        "aciertos": 1, "mejor": a["conf"], "verso_bd": a["verso"], "oido": a["oido"],
                        "aviso": a["aviso"]})
    # Un bloque de un solo acierto de otra canción partía el de la buena; una vez fuera, se
    # vuelven a fundir los seguidos de la misma canción.
    fundidos: list[dict] = []
    for b in (b for b in bloques if b["aciertos"] >= 2 and b["mejor"] >= MEJOR_MINIMO):
        prev = fundidos[-1] if fundidos else None
        if prev and prev["k"] == b["k"] and b["inicio_s"] - prev["fin_s"] <= 120:
            prev["fin_s"], prev["aciertos"] = b["fin_s"], prev["aciertos"] + b["aciertos"]
            prev["mejor"] = max(prev["mejor"], b["mejor"])
            continue
        fundidos.append(b)
    return fundidos, descartes


def mmss(s: float) -> str:
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", required=True)
    ap.add_argument("--artista")
    ap.add_argument("--concierto", help="fecha · lugar, tal como consta")
    ap.add_argument("--anio", type=int, help="año del concierto (guarda de canciones posteriores)")
    ap.add_argument("--desde-json", action="store_true",
                    help="reprocesar los segmentos ya guardados, sin descargar ni pagar Whisper")
    args = ap.parse_args()
    ruta = os.path.join(SALIDA, f"{args.id}.json")
    os.makedirs(SALIDA, exist_ok=True)

    if args.desde_json:
        with open(ruta, encoding="utf-8") as fh:
            resultado = json.load(fh)
        segmentos = resultado["segmentos"]
    else:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        url = f"https://www.youtube.com/watch?v={args.id}"
        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, "concierto.mp3")
            descargar(url, audio)
            minutos = duracion(audio) / 60
            logger.info("%s · %.1f min ≈ %.2f $", url, minutos, minutos * COSTE_POR_MINUTO)
            segmentos = transcribir(audio, client)
        resultado = {"video": url, "artista": args.artista, "concierto": args.concierto,
                     "minutos": round(minutos, 1), "coste_usd": round(minutos * COSTE_POR_MINUTO, 2),
                     "comprobado_en": datetime.now().strftime("%Y-%m-%d %H:%M"),
                     "n_segmentos": len(segmentos), "segmentos": segmentos}
    if args.anio:
        resultado["anio"] = args.anio

    with SessionLocal() as db:
        catalogo = momentos.cargar_catalogo(db)
        anios = anios_de_estreno(db)
    bloques, descartes = setlist(segmentos, catalogo, anios, resultado.get("anio"))
    resultado["setlist"], resultado["descartes_por_fecha"] = bloques, descartes
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=1)
    for b in bloques:
        logger.info("%s  %-40s  (%d aciertos, mejor %.2f) %s", mmss(b["inicio_s"]), b["cancion"],
                    b["aciertos"], b["mejor"], b.get("aviso", ""))
    for d in descartes[:10]:
        logger.info("descartado: %s", d)
    logger.info("%d canciones · %d descartes por fecha · %d segmentos", len(bloques),
                len(descartes), len(segmentos))


if __name__ == "__main__":
    main()
