"""Extrae CANDIDATOS de autoría del corpus. No afirma nada: propone y adjunta prueba.

    docker compose exec api python -m scripts.pr.mine_authorship --out /tmp/estudio

`song_credits` está vacía de facto (2 filas) y el verificador por consenso
(`scripts/verify/authorship_consensus.py`) funciona pero no tiene qué masticar: su
YAML de hipótesis trae UNA. Esto llena esa entrada leyendo lo que ya está ingerido.

El pilar del estudio que alimenta es «los poetas que escribieron Extremoduro»: el
modelo del sitio asumía que todo texto era de Robe y es falso — hay poemas de otros
que Robe musicó (Chinato), estrofas prestadas (Lorca dentro de «Puta») y poemas
recitados (Marcos Ana en «Te juzgarán sólo por tus errores»).

**Lo que sale de aquí es una PROPUESTA con su cita.** Se revisa a mano, se pega en
`data/song_credits.yaml` con `status: pending_verification` y es el consenso
multi-fuente quien decide si se escribe. Mismo criterio que el resto del proyecto:
lo que no se corrobora no se publica, y lo que no casa no se adivina.

DOS PASADAS, y no es un capricho:
  1. **Descubrir** nombres de autor con mayúsculas, en las fuentes que las tienen
     (blog, prensa, anotaciones de Genius, entrevistas transcritas a mano).
  2. **Buscar** esos nombres en TODO el corpus sin distinguir mayúsculas, porque las
     transcripciones automáticas de YouTube vienen en minúscula («manolillo chinato
     presenta el libro…») y ahí un extractor de nombres propios no ve nada. Son 330
     de las 698 fuentes: dejarlas fuera sería tirar la mitad del material.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy import text as sqltext

from app.db.models import Album, Artist, Song
from app.db.session import SessionLocal
from app.services.kw_normalize import kw_norm, strip_title_suffix

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Fuentes que conservan las mayúsculas. Las transcripciones NO entran aquí.
KINDS_CON_MAYUSCULAS = ("blog", "press", "genius_annotation", "robe_interview", "about_robe")

# Fórmulas que anuncian una autoría ajena, con el rol que sugieren. El orden
# importa: la primera que case manda.
FORMULAS: tuple[tuple[str, str], ...] = (
    (r"poemas?\s+(?:de|del)\s+", "poema_original"),
    (r"(?:el\s+)?texto\s+(?:es\s+)?(?:de|del)\s+", "poema_original"),
    (r"versos?\s+(?:de|del)\s+", "poema_original"),
    (r"(?:la\s+)?letra\s+(?:es\s+)?(?:de|del)\s+", "letra"),
    (r"escrit[oa]\s+por\s+", "letra"),
    (r"(?:de|del)\s+su\s+libro\s+", "poema_original"),
    (r"musicad[oa]\s+por\s+", "musica"),
    (r"musicó\s+", "musica"),
    (r"adaptación\s+(?:de|del)\s+", "adaptacion"),
    # «contiene una estrofa de…», «se citan un par de fragmentos de…»
    (r"estrofas?\s+(?:de|del)\s+", "poema_original"),
    (r"fragmentos?\s+(?:de|del)\s+", "poema_original"),
    (r"extraíd[oa]s?\s+(?:de|del)\s+", "poema_original"),
    (r"recitó\s+", "poema_original"),
)

# Entre la fórmula y el nombre puede haber relleno, y por no contemplarlo se caía
# el caso de Lorca: Jot Down escribe «escrito por UN JOVEN Federico García Lorca»,
# y pedir el nombre pegado a «escrito por» no casaba nada.
RELLENO = r"(?:(?:un|una|el|la|los|las|su|sus|joven|gran|poeta|escritor|autor)\s+){0,3}"

# Un nombre propio: dos a cuatro palabras capitalizadas. Pedir DOS evita que
# «De» o «Robe» sueltos pasen por nombre, y es la misma cautela que
# `kw_normalize` aplica a las personas (un nombre de pila suelto es homónimo puro).
NOMBRE = r"([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑáéíóúüñ'\.]+(?:\s+(?:de\s+|del\s+|la\s+)?[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑáéíóúüñ'\.]+){1,3})"

# Ni el sujeto del sitio ni sus bandas son «un poeta ajeno».
NO_SON_AUTORES_AJENOS = {
    "robe", "roberto iniesta", "extremoduro", "robe iniesta", "iniesta ojea",
    "uoho", "inaki anton", "inaki uoho anton", "el drogas", "fito cabrales",
}
# Ruido que la regex de nombre propio recoge al empezar una frase.
RUIDO = {
    "el", "la", "los", "las", "un", "una", "este", "esta", "ese", "esa", "su",
    "mi", "no", "si", "y", "o", "pero", "como", "cuando", "donde", "por", "para",
    "en", "con", "sin", "sobre", "del", "de", "al", "a", "que", "es", "son",
}

# Ventana para buscar la canción alrededor del autor. La primera versión usaba 420
# y la precisión era mala: el artículo de Jot Down enumera en un párrafo a Machado,
# Neruda, Miguel Hernández y Lorca junto a varias canciones, y el producto cartesiano
# salía entero («So payaso» atribuida a los tres a la vez). Con 180 el autor y el
# título tienen que estar en la misma frase o la de al lado.
VENTANA = 180
# Un párrafo con tres o más autores, o tres o más canciones, es un repaso de
# influencias, no una atribución. No se descarta —puede llevar dentro la buena— pero
# se marca y se ordena por detrás.
MAX_AUTORES_VENTANA = 3
MAX_TITULOS_VENTANA = 3
MIN_TITULO_CORTO = 10  # por debajo, el título solo casa como palabra completa


def _sin_acentos(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def descubrir_autores(db) -> dict[str, int]:
    """Pasada 1: nombres que aparecen DETRÁS de una fórmula de autoría."""
    filas = db.execute(sqltext(
        "select content_clean from interpretation_sources "
        "where kind = any(:kinds) and content_clean is not null"
    ), {"kinds": list(KINDS_CON_MAYUSCULAS)}).all()

    cuenta: dict[str, int] = defaultdict(int)
    for (txt,) in filas:
        for formula, _rol in FORMULAS:
            for m in re.finditer(formula + RELLENO + NOMBRE, txt):
                nombre = re.sub(r"\s+", " ", m.group(1)).strip(" .,;:")
                base = _sin_acentos(nombre)
                if base in NO_SON_AUTORES_AJENOS:
                    continue
                if base.split()[0] in RUIDO:
                    continue
                cuenta[nombre] += 1
    logger.info("pasada 1: %d nombres distintos tras una fórmula de autoría", len(cuenta))
    return dict(cuenta)


def candidatos(db, autores: dict[str, int], comps: dict) -> list[dict]:
    """Pasada 2: co-aparición de autor + canción + fórmula, en TODO el corpus."""
    filas = db.execute(sqltext(
        "select id, kind, title, url, content_clean from interpretation_sources "
        "where content_clean is not null"
    )).all()

    # Índice de títulos. Cada canción aporta su título completo Y su cola
    # distintiva, porque el corpus no escribe los títulos como la BD: la gente
    # dice «Ama, ama y ensancha el alma» con dos «ama» y la BD tiene tres, así
    # que el literal no casaba y el caso más conocido del proyecto —el poema de
    # Chinato— se caía del minado.
    titulos = []
    for c in comps.values():
        claves = set()
        t = _sin_acentos(c["titulo"])
        if len(t) >= 4:
            claves.add(t)
        palabras = t.split()
        if len(palabras) >= 4:
            cola = " ".join(palabras[-3:])
            if len(cola) >= 12:
                claves.add(cola)
        for k in claves:
            titulos.append((k, c))

    salida: dict[tuple[str, str], dict] = {}
    for sid, kind, stitle, url, txt in filas:
        bajo = _sin_acentos(txt)
        for autor in autores:
            a = _sin_acentos(autor)
            for m in re.finditer(re.escape(a), bajo):
                ini, fin = max(0, m.start() - VENTANA), m.start() + VENTANA
                ventana, ventana_cruda = bajo[ini:fin], txt[ini:fin]
                rol = next((r for f, r in FORMULAS if re.search(f, ventana)), None)
                if not rol:
                    continue
                # ¿Es un repaso de influencias? Se mide antes de emitir nada.
                otros_autores = sum(1 for o in autores if _sin_acentos(o) in ventana)
                en_ventana = {c["clave"] for t, c in titulos if t in ventana}
                es_lista = otros_autores >= MAX_AUTORES_VENTANA or len(en_ventana) >= MAX_TITULOS_VENTANA
                for t, comp in titulos:
                    # Un título corto dentro de prosa arrastra medio diccionario
                    # («salir», «puta»): solo casa como palabra completa. Es la
                    # misma cautela de youtube_relevance y kw_normalize.
                    patron = rf"\b{re.escape(t)}\b" if len(t) < MIN_TITULO_CORTO else re.escape(t)
                    if not re.search(patron, ventana):
                        continue
                    clave = (comp["clave"], autor)
                    ficha = salida.setdefault(clave, {
                        "song_title": comp["titulo"],
                        "album_slug": comp["album_slug"],
                        "disco": comp["disco"],
                        "anyo": comp["anyo"],
                        "autor": autor,
                        "roles": set(),
                        "apariciones": 0,
                        "fuentes": [],
                    })
                    ficha["roles"].add(rol)
                    ficha["apariciones"] += 1
                    ficha["en_lista"] = ficha.get("en_lista", 0) + (1 if es_lista else 0)
                    ficha["en_frase"] = ficha.get("en_frase", 0) + (0 if es_lista else 1)
                    if len(ficha["fuentes"]) < 4 and not any(f["source_id"] == sid for f in ficha["fuentes"]):
                        ficha["fuentes"].append({
                            "source_id": sid, "kind": kind,
                            "title": (stitle or "")[:110], "url": url,
                            "cita": re.sub(r"\s+", " ", ventana_cruda).strip()[:340],
                        })

    out = []
    for ficha in salida.values():
        ficha["roles"] = sorted(ficha["roles"])
        ficha["kinds"] = sorted({f["kind"] for f in ficha["fuentes"]})
        # Una sola transcripción automática no basta: traen erratas conocidas
        # («Robben y Niesta» por «Robe Iniesta»).
        ficha["solo_transcripcion"] = ficha["kinds"] == ["youtube_transcript"]
        ficha.setdefault("en_lista", 0)
        ficha.setdefault("en_frase", 0)
        # Una anotación de Genius comenta un verso concreto: es la fuente de más
        # precisión que hay para esto.
        ficha["tiene_genius"] = "genius_annotation" in ficha["kinds"]
        if ficha["en_frase"] == 0:
            ficha["calidad"] = "solo_en_lista_de_influencias"
        elif ficha["tiene_genius"] or (ficha["en_frase"] >= 2 and not ficha["solo_transcripcion"]):
            ficha["calidad"] = "fuerte"
        elif ficha["solo_transcripcion"]:
            ficha["calidad"] = "debil_solo_transcripcion"
        else:
            ficha["calidad"] = "revisar"
        out.append(ficha)
    orden = {"fuerte": 0, "revisar": 1, "debil_solo_transcripcion": 2,
             "solo_en_lista_de_influencias": 3}
    out.sort(key=lambda f: (orden[f["calidad"]], -f["en_frase"], -len(f["fuentes"])))
    return out


def catalogo(db) -> dict:
    comps: dict[str, dict] = {}
    for titulo, disco, album_slug, anyo in db.execute(
        select(Song.title, Album.title, Album.slug, Album.year)
        .join(Album, Album.id == Song.album_id)
        .join(Artist, Artist.id == Album.artist_id)
    ).all():
        k = kw_norm(strip_title_suffix(titulo))
        prev = comps.get(k)
        if prev is None or (anyo or 9999) < prev["anyo"]:
            comps[k] = {"clave": k, "titulo": strip_title_suffix(titulo),
                        "disco": disco, "album_slug": album_slug, "anyo": anyo or 0}
    return comps


def yaml_propuesta(cands: list[dict]) -> str:
    """Bloque listo para pegar en data/song_credits.yaml tras revisarlo."""
    out = ["# Candidatos extraídos del corpus por scripts.pr.mine_authorship.",
           "# REVISAR UNO A UNO antes de pegarlos. Siguen en pending_verification:",
           "# los escribe el consenso, no esto.", "credits:"]
    for c in cands:
        if c["calidad"] == "solo_en_lista_de_influencias":
            continue
        rol = c["roles"][0]
        out += [
            f'  - song_title: "{c["song_title"]}"',
            f'    album_slug: {c["album_slug"]}',
            f'    source: corpus_mining',
            f'    status: pending_verification',
            f'    credits:',
            f'      - role: {rol}',
            f'        name: "{c["autor"]}"',
            f'        primary: true',
            f'        note: "{c["calidad"]} · {len(c["fuentes"])} fuente(s): {", ".join(c["kinds"])}"',
        ]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-fuentes", type=int, default=1)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        comps = catalogo(db)
        autores = descubrir_autores(db)
        cands = candidatos(db, autores, comps)

    cands = [c for c in cands if len(c["fuentes"]) >= args.min_fuentes]
    (out / "autoria_candidatos.json").write_text(
        json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "autoria_propuesta.yaml").write_text(yaml_propuesta(cands), encoding="utf-8")

    logger.info("%d candidatos (canción × autor) escritos en %s", len(cands), out)
    print()
    from collections import Counter
    print("Reparto por calidad de la prueba:")
    for k, v in Counter(c["calidad"] for c in cands).most_common():
        print(f"   {v:>3}  {k}")
    print()
    print(f"{'CANCIÓN':<36}{'AUTOR':<24}{'ROL':<16}{'FRASE':>6}{'LISTA':>6}  CALIDAD · FUENTES")
    print("-" * 118)
    for c in cands:
        if c["calidad"] == "solo_en_lista_de_influencias":
            continue
        print(f'{c["song_title"][:34]:<36}{c["autor"][:22]:<24}{c["roles"][0]:<16}'
              f'{c["en_frase"]:>6}{c["en_lista"]:>6}  {c["calidad"]:<26} {",".join(c["kinds"])[:40]}')
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
