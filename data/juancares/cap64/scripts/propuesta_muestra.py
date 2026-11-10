"""Propuesta para la MUESTRA de 10 candidatas (paso 3 + 4b del plan del 10-11-2026).

No crea nada. Toda la evidencia está en `analisis_personas/` y cada hecho lleva el
id de su fuente (tabla FUENTES). Los title/description se pasan por
`app.services.seo_style.title_verdict` / `desc_verdict` contra el ESQUELETO
propuesto (H2 + hechos afirmables), porque la ficha todavía no existe.

Uso (desde la raíz del repo):
  python data/juancares/cap64/scripts/propuesta_muestra.py data/juancares/cap64
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "api"))
from app.services import seo_style  # noqa: E402

BASE = Path(sys.argv[1])
OUT = BASE / "analisis_personas"
VOL = json.loads((OUT / "volumenes_muestra.json").read_text())["por_persona"]

# --------------------------------------------------------------------------- #
# Fuentes. Tipo: PROPIA (nuestra BD), WEB (externa descargada), CORPUS (ajena,
# otro autor), TESTIMONIO (la persona hablando de sí misma en el vídeo 1756),
# FONDO (el narrador del vídeo u otros vídeos del mismo autor: orienta, no afirma).
# --------------------------------------------------------------------------- #
FUENTES = {
    "W-ELIA": ("WEB", "es.wikipedia «Elía María Blanco Barbero» (Q5830178)",
               "https://es.wikipedia.org/wiki/El%C3%ADa_Mar%C3%ADa_Blanco_Barbero", "wiki_check.json"),
    "W-EXT": ("WEB", "es.wikipedia «Extremoduro»", "https://es.wikipedia.org/wiki/Extremoduro", "wiki_check.json"),
    "W-ROBE": ("WEB", "es.wikipedia «Roberto Iniesta»", "https://es.wikipedia.org/wiki/Roberto_Iniesta", "wiki_check.json"),
    "W-SUA": ("WEB", "es.wikipedia «Somos unos animales» (créditos)", "https://es.wikipedia.org/wiki/Somos_unos_animales", "wiki_check.json"),
    "W-DEL": ("WEB", "es.wikipedia «Deltoya» (créditos)", "https://es.wikipedia.org/wiki/Deltoya", "wiki_check.json"),
    "W-DEMA": ("WEB", "es.wikipedia «¿Dónde están mis amigos?» (créditos)",
               "https://es.wikipedia.org/wiki/%C2%BFD%C3%B3nde_est%C3%A1n_mis_amigos%3F", "wiki_check.json"),
    "W-GEF": ("WEB", "es.wikipedia «Grandes éxitos y fracasos» (nota de pistas)",
              "https://es.wikipedia.org/wiki/Grandes_%C3%A9xitos_y_fracasos", "wiki_check.json"),
    "FORBES": ("WEB", "Forbes España, 11-03-2025: «realizada por el artista placentino Jesús Mateos Brea»",
               "https://forbes.es/actualidad/647538/el-mural-el-descendimiento-de-plasencia-reconocido-como-el-mejor-mural-del-mundo/",
               "descargada el 10-11-2026"),
    "MS-366": ("CORPUS", "Mondo Sonoro: extracto de «Talento innato» (corpus prod id 366)", "", "menciones_muestra_detalle.tsv"),
    "TR-404": ("CORPUS", "Trembol, homenaje a Robe, cita en 1.ª persona de Robe (corpus prod ids 404/472)", "",
               "menciones_muestra_detalle.tsv"),
    "PR-431": ("CORPUS", "«Fallecimiento de Robe (2025) y homenajes póstumos», prensa (corpus prod id 431)", "",
               "menciones_muestra_detalle.tsv"),
    "BD": ("PROPIA", "BD de prod: albums / persons / places", "", "catalogo_relaciones_prod.txt"),
    "JC": ("FONDO", "Otros vídeos de Juancares en el corpus (mismo autor que la 1756)", "", "menciones_muestra_detalle.tsv"),
}


def T(minuto: str) -> str:
    """Testimonio de primera mano en la fuente 1756, comprobado por texto."""
    return f"TESTIMONIO@{minuto}"


def V(minuto: str) -> str:
    """Lo dice el narrador del vídeo 1756: fondo, no se afirma."""
    return f"FONDO@{minuto}"


# Cada hecho: (texto, [fuentes]). Es AFIRMABLE si tiene al menos una fuente WEB,
# CORPUS, PROPIA o TESTIMONIO. Solo FONDO → orienta, no se escribe.
MUESTRA = [
    {
        "id": "E-020", "nombre": "Elia Blanco", "nombre_completo": "Elía María Blanco Barbero",
        "slug": "elia-blanco", "grupo": "figura pública", "qid": "Q5830178",
        "hechos": [
            ("Nace en Cabezuela del Valle el 20-01-1964", ["W-ELIA"]),
            ("Concejala del Ayuntamiento de Plasencia entre 1987 y 1991", ["W-ELIA"]),
            ("Alcaldesa de Plasencia (PSOE) entre 2003 y 2011; sucede a José Luis Díaz Sánchez y le sucede Fernando Pizarro", ["W-ELIA", "MS-366"]),
            ("Conocía a Robe desde antes de ser concejala (por una amiga de una empresa de repuestos)", [T("1:38:30")]),
            ("Concejala de Juventud en 1989 y gestora del concierto de la COPE", [V("1:35:47")]),
            ("Con ella de alcaldesa vuelve Extremoduro a Plasencia (2008)", [V("2:42:44"), "MS-366"]),
            ("Condenada en 2015 por fraude y prevaricación (Wikipedia)", ["W-ELIA"]),
        ],
        "kw": "elia blanco", "kw_sec": ["elia maria blanco", "elia blanco extremoduro"],
        "title": "Elia Blanco: alcaldesa de Plasencia y amiga de Robe",
        "desc": "Conoce a Elia Blanco, concejala y alcaldesa de Plasencia, y su papel en la relación entre la ciudad, Robe y Extremoduro.",
        "h2": ["Quién es Elia Blanco", "Concejala en Plasencia (1987-1991)", "Su relación con Robe",
               "Alcaldesa de Plasencia (2003-2011) y la vuelta de Extremoduro"],
        "recomendacion": "crear (con decisión previa de David)",
        "motivo": ("Material suficiente: artículo propio en Wikipedia + Mondo Sonoro + testimonio propio. "
                   "DECISIÓN: es una figura pública viva con condena por corrupción en Wikipedia; o se menciona "
                   "con su fuente o la ficha no se hace. Omitirla en una biografía sería sesgar."),
    },
    {
        "id": "E-028", "nombre": "José Luis Díaz", "nombre_completo": "José Luis Díaz Sánchez",
        "slug": "jose-luis-diaz-sanchez", "grupo": "figura pública", "qid": None,
        "hechos": [
            ("Alcalde de Plasencia del PP; en 2003 deja de serlo y le sucede Elia Blanco", ["MS-366", "W-ELIA"]),
            ("En 2003 encabeza Compromiso por Plasencia, escindida del PP", ["W-ELIA"]),
            ("Vetó a Extremoduro en Plasencia; Robe le escribió una carta recriminándole la censura", ["W-EXT", "MS-366"]),
            ("Canceló el concierto de Dover (2000) y anunció una «censura previa» de letras", [V("2:31:49"), V("2:32:01")]),
            ("Antes fue presidente de la UP Plasencia", [V("2:17:37")]),
        ],
        "kw": "jose luis diaz plasencia", "kw_sec": ["alcalde de plasencia extremoduro"],
        "title": "José Luis Díaz Sánchez: el alcalde que vetó a Extremoduro",
        "desc": "Descubre quién fue José Luis Díaz Sánchez, el alcalde de Plasencia que vetó a Extremoduro, y la carta con la que Robe le respondió.",
        "h2": ["Quién es José Luis Díaz Sánchez", "El veto a Extremoduro en Plasencia",
               "La carta de Robe", "El fin de su etapa (2003)"],
        "recomendacion": "crear",
        "motivo": "Suficiente: veto documentado en Wikipedia y Mondo Sonoro. Sin artículo propio ni QID: sameAs vacío.",
    },
    {
        "id": "E-039", "nombre": "Paco Doniga", "nombre_completo": "Paco Doniga",
        "slug": "paco-doniga", "grupo": "escena", "qid": None,
        "hechos": [
            ("Bajista puntual de Dosis Letal, el primer grupo de Robe (1983)", ["W-EXT", "W-ROBE", T("0:38:48")]),
            ("Tocó con Dosis Letal en un festival en el campo de fútbol; el repertorio, «cuatro o cinco» temas, incluía alguno de Rory Gallagher", [T("0:39:06"), T("0:39:20")]),
            ("Robe le hizo una dedicatoria «desde los Dosis Letal hasta aquí» (el testimonio no dice en qué)", [T("0:39:37")]),
            ("Convenció a Robe para que cantara él sus canciones", [V("0:39:56"), "JC"]),
            ("Tesorero del Colectivo de Músicos y técnico de sonido de los primeros Extremoduro", [V("1:02:09"), V("1:26:42")]),
        ],
        "kw": "paco doniga", "kw_sec": ["paco doniga extremoduro", "dosis letal robe"],
        "title": "Paco Doniga: el bajista de Dosis Letal, primer grupo de Robe",
        "desc": "Conoce a Paco Doniga, bajista de Dosis Letal, el primer grupo de Robe, y su papel en los comienzos de Extremoduro en Plasencia.",
        "h2": ["Quién es Paco Doniga", "Bajista de Dosis Letal", "El concierto del campo de fútbol",
               "La dedicatoria de Robe"],
        "recomendacion": "crear",
        "motivo": ("Suficiente: Wikipedia (dos artículos) + testimonio propio largo. Grafía: Wikipedia escribe "
                   "«Doniga»; Whisper «Dónica/Dóniga». Se usa la de Wikipedia."),
    },
    {
        "id": "E-037", "nombre": "Juano", "nombre_completo": "Juano",
        "slug": "juano", "grupo": "escena", "qid": None,
        "hechos": [
            ("Vocalista de Dosis Letal (1983), con Luisma Beltrán, Zósimo «Zosi» Pascual y Paco Doniga", ["W-EXT", "W-ROBE"]),
            ("Cantante en los primeros ensayos de lo que sería Extremoduro", [V("0:39:47"), "JC"]),
        ],
        "kw": "dosis letal", "kw_sec": ["dosis letal robe", "dosis letal extremoduro"],
        "title": "", "desc": "", "h2": [],
        "recomendacion": "no crear ficha propia: sección en la futura página de Dosis Letal",
        "motivo": ("Un solo dato afirmable y sin apellido. La demanda está en el grupo («dosis letal» 170, "
                   "«dosis letal robe» 70) y no en él: Dosis Letal pasa a la fase de grupos."),
    },
    {
        "id": "E-040", "nombre": "Ángel Lorenzo", "nombre_completo": "Ángel Lorenzo",
        "slug": "angel-lorenzo", "grupo": "escena", "qid": None,
        "hechos": [
            ("Primer batería de Extremoduro (1987), con Robe y Kaíto; duró unos cuatro meses y le sustituyó William",
             ["W-EXT", "TR-404", T("0:54:44")]),
            ("Aportó una grabación de un ensayo de comienzos de 1987", ["W-EXT"]),
            ("Robe le propuso tocar en el Jazz de Luis «von Fanta», donde hacían jam", [T("0:54:44")]),
            ("Ensayaban en los locales de la Casa de la Salud", [T("0:55:19")]),
        ],
        "kw": "angel lorenzo extremoduro", "kw_sec": ["primer bateria de extremoduro"],
        "title": "Ángel Lorenzo: el primer batería de Extremoduro",
        "desc": "Descubre cómo Ángel Lorenzo tocó la batería en los primeros ensayos de Extremoduro, con Robe y Kaíto, en la Plasencia de 1987.",
        "h2": ["Quién es Ángel Lorenzo", "El primer batería de Extremoduro (1987)",
               "Del Jazz a la Casa de la Salud", "Por qué le sustituyó William"],
        "recomendacion": "crear + alta en band_memberships (Extremoduro, batería, 1987)",
        "motivo": ("Suficiente: Wikipedia + Robe citado por Trembol + testimonio propio. Completa la formación: "
                   "hoy la BD empieza en William. El «por qué lo dejó» solo lo cuenta el vídeo: comprobar en su testimonio."),
    },
    {
        "id": "E-050", "nombre": "María Timón", "nombre_completo": "María Timón",
        "slug": "maria-timon", "grupo": "escena", "qid": None,
        "hechos": [
            ("Coros en «Somos unos animales» (1991): Tu corazón, Quemando tus recuerdos, Desidia", ["W-SUA", "BD"]),
            ("Voces en «Deltoya» (1992): Sol de invierno, Con un latido del reloj, Papel secante, Ama, ama, ama y ensancha el alma", ["W-DEL", "BD"]),
            ("Sus voces originales se conservan en «Grandes éxitos y fracasos» (2004)", ["W-GEF"]),
            ("Conoció a Robe en el Bar Tertulia, con Belén", [V("1:10:38"), T("1:10:50")]),
        ],
        "kw": "maria timon", "kw_sec": ["coristas de extremoduro"],
        "title": "María Timón: la corista de Somos unos animales y Deltoya",
        "desc": "Conoce a María Timón, la corista que puso voz en Somos unos animales y Deltoya junto a Belén, y en qué canciones de Extremoduro canta.",
        "h2": ["Quién es María Timón", "Coros en Somos unos animales (1991)", "Voces en Deltoya (1992)",
               "Del Bar Tertulia a Extremoduro"],
        "recomendacion": "crear + créditos en canciones (SongCredit «coros»)",
        "motivo": "Justo pero sólido: créditos en Wikipedia por canción. Los créditos van aunque no haya ficha.",
    },
    {
        "id": "E-049", "nombre": "Belén", "nombre_completo": "Belén",
        "slug": "", "grupo": "escena", "qid": None,
        "hechos": [
            ("Coros/voces en «Somos unos animales», «Deltoya» y «¿Dónde están mis amigos?»", ["W-SUA", "W-DEL", "W-DEMA"]),
            ("Cantaba con María los temas de Marcos Peral en el Tertulia", [T("1:10:50")]),
            ("Cantó coros en el concierto de Plasencia de 1995", [V("2:21:56")]),
        ],
        "kw": "belen extremoduro", "kw_sec": [],
        "title": "", "desc": "", "h2": [],
        "recomendacion": "créditos sí; ficha cuando se sepa el apellido",
        "motivo": "Ninguna fuente da su apellido: una ficha «Belén» no se puede identificar ni desambiguar.",
    },
    {
        "id": "E-055", "nombre": "Susi Iglesias", "nombre_completo": "Susi Iglesias",
        "slug": "", "grupo": "escena", "qid": None,
        "hechos": [
            ("Aportó dibujos al primer disco de Extremoduro, con su compañero Gustavo; llegaron por Miguel Ángel Corisco «Cori»", [T("1:58:35")]),
            ("El buitre y la bellota del primer disco", [V("1:57:53")]),
        ],
        "kw": "susi iglesias", "kw_sec": [],
        "title": "", "desc": "", "h2": [],
        "recomendacion": "no crear ficha: sección «la portada» en «Tú en tu casa, nosotros en la hoguera» + crédito",
        "motivo": ("Solo su testimonio; la web no la nombra. Hay demanda de portadas en las fichas de disco "
                   "(GSC: «portadas discos extremoduro», 117 impresiones). [HIPÓTESIS] que el «primer disco» del que habla sea "
                   "«Tú en tu casa…» (1990, el primero por año en la BD): confirmarlo en su testimonio."),
    },
    {
        "id": "E-047", "nombre": "Paramio", "nombre_completo": "Paramio",
        "slug": "", "grupo": "escena", "qid": None,
        "hechos": [
            ("«Uno de los cofundadores de Extremoduro», según Mondo Sonoro", ["MS-366"]),
            ("Dueño de La Cuadra, «hilo invisible» de la escena rock", [V("1:07:40"), "JC"]),
        ],
        "kw": "paramio extremoduro", "kw_sec": [],
        "title": "", "desc": "", "h2": [],
        "recomendacion": "identificar antes",
        "motivo": ("Mondo Sonoro lo llama cofundador de Extremoduro, y ni la BD ni Wikipedia lo cuentan así: "
                   "hay que aclararlo antes de afirmar nada. Sin nombre de pila. (Jot Down: falso positivo, «Fernando Paramio» firma un artículo.)"),
    },
    {
        "id": "E-048", "nombre": "Javi Génesis", "nombre_completo": "Javi Gómez «Javi Génesis»",
        "slug": "", "grupo": "escena", "qid": None,
        "hechos": [
            ("Dueño del Tertulia y del Génesis; Robe fue camarero en sus bares", [V("1:10:12"), "JC"]),
        ],
        "kw": "", "kw_sec": [],
        "title": "", "desc": "", "h2": [],
        "recomendacion": "no crear: sus bares entran en la fase de lugares",
        "motivo": "Insuficiente: solo vídeos del mismo autor; la web no lo corrobora.",
    },
    {
        "id": "E-068", "nombre": "Jesús Mateos Brea", "nombre_completo": "Jesús Mateos Brea",
        "slug": "jesus-mateos-brea", "grupo": "escena", "qid": None,
        "hechos": [
            ("Artista placentino; autor del mural «El Descendimiento» (Plasencia, 2025)", ["FORBES"]),
            ("Autor del macromural de Plasencia que une el legado de Robe con la poesía de Manolo Chinato", ["PR-431", "JC"]),
            ("El mural está en la plaza Puerto de Béjar", [V("3:24:28")]),
        ],
        "kw": "jesus mateos brea", "kw_sec": ["mural robe plasencia"],
        "title": "Jesús Mateos Brea: el mural de Robe y Chinato en Plasencia",
        "desc": "Descubre el mural de Jesús Mateos Brea en Plasencia, el homenaje que une la palabra de Robe con la poesía de Manolo Chinato.",
        "h2": ["Quién es Jesús Mateos Brea", "El mural de Robe y Manolo Chinato", "Otros murales en Plasencia"],
        "recomendacion": "crear (y valorar una página del mural)",
        "motivo": ("Suficiente. «mural robe plasencia» (170) es mayor que su nombre (40), pero en Plasencia hay OTRO "
                   "mural de Robe, de Primo (resultado web del 10-11): la página del mural tiene que desambiguar."),
    },
]

# --------------------------------------------------------------------------- #
# Matriz de relaciones (paso 4b). Destino con @id; «pendiente» si la entidad
# destino no existe todavía. Evidencia = ids de FUENTES / minutos.
# --------------------------------------------------------------------------- #
S = "https://entreinteriores.com"
RELACIONES = [
    # (persona, propiedad, inversa, destino, @id destino, evidencia, estado del dato)
    ("E-020", "jobTitle / worksFor", "employee", "Ayuntamiento de Plasencia (concejala 1987-1991; alcaldesa 2003-2011)", "Organization sin página → Wikidata del Ayuntamiento [por resolver]", "W-ELIA", "no existe: tabla de relaciones"),
    ("E-020", "birthPlace", "—", "Cabezuela del Valle", "pendiente (sin /lugares); containedInPlace /lugares/valle-del-jerte#place", "W-ELIA", "no existe: lugar nuevo"),
    ("E-020", "knows", "knows", "Robe", f"{S}/personas/robe-iniesta#person", T("1:38:30"), "no existe: tabla de relaciones"),
    ("E-020", "sameAs", "—", "Wikipedia + Wikidata", "https://www.wikidata.org/wiki/Q5830178", "W-ELIA", "se rellena en seed_persons"),
    ("E-028", "jobTitle / worksFor", "employee", "Ayuntamiento de Plasencia (alcalde hasta 2003)", "ídem E-020", "MS-366 · W-ELIA", "no existe: tabla de relaciones"),
    ("E-028", "memberOf", "member", "Partido Popular; Compromiso por Plasencia (2003)", "Wikidata [por resolver]", "MS-366 · W-ELIA", "no existe"),
    ("E-028", "subjectOf", "about", "La carta de Robe al alcalde", "pendiente (CreativeWork sin página)", "W-EXT", "no existe"),
    ("E-028", "relatedTo", "relatedTo", "Extremoduro (veto)", f"{S}/extremoduro#musicgroup", "W-EXT", "no existe: tabla de relaciones"),
    ("E-039", "memberOf (OrganizationRole: bajo, 1983)", "member", "Dosis Letal", "pendiente (/grupos/dosis-letal#musicgroup, fase grupos)", "W-EXT · W-ROBE", "no existe: grupo nuevo"),
    ("E-039", "colleague", "colleague", "Robe", f"{S}/personas/robe-iniesta#person", "W-ROBE · " + T("0:39:37"), "derivable de membresía común"),
    ("E-039", "colleague", "colleague", "Juano, Luisma Beltrán, Zósimo «Zosi» Pascual", "pendiente (sin ficha)", "W-EXT", "derivable de membresía común"),
    ("E-037", "memberOf (OrganizationRole: voz, 1983)", "member", "Dosis Letal", "pendiente (fase grupos)", "W-EXT · W-ROBE", "no existe: grupo nuevo"),
    ("E-040", "memberOf (OrganizationRole: batería, 1987)", "member", "Extremoduro", f"{S}/extremoduro#musicgroup", "W-EXT · TR-404 · " + T("0:54:44"), "band_memberships (existe la tabla)"),
    ("E-040", "colleague", "colleague", "Robe; Kaíto; William (le sustituye)", f"{S}/personas/robe-iniesta#person · /personas/kaito#person · /personas/william-extremoduro#person", "W-EXT", "derivable de membresía"),
    ("E-040", "knows", "knows", "Luis «von Fanta» (el Jazz)", f"{S}/personas/luis-von-fanta#person", T("0:54:44"), "no existe: tabla de relaciones"),
    ("E-040", "workLocation / Event", "location", "Casa de la Salud (local de ensayo)", "pendiente (fase lugares)", T("0:55:19"), "no existe: lugar nuevo"),
    ("E-050", "contributor (roleName: coros) en MusicRecording", "—", "Tu corazón · Quemando tus recuerdos · Desidia", f"{S}/extremoduro/somos-unos-animales/tu-corazon (y las otras dos)", "W-SUA", "SongCredit (existe la tabla)"),
    ("E-050", "contributor (voces) en MusicRecording", "—", "Sol de invierno · Con un latido del reloj · Papel secante · Ama, ama, ama…", f"{S}/extremoduro/deltoya/<canción>", "W-DEL", "SongCredit (existe la tabla)"),
    ("E-050", "contributor en MusicAlbum", "—", "Somos unos animales; Deltoya; Grandes éxitos y fracasos", f"{S}/extremoduro/somos-unos-animales#album …", "W-SUA · W-DEL · W-GEF", "derivable de SongCredit"),
    ("E-050", "colleague", "colleague", "Belén", "pendiente (sin ficha)", "W-SUA · W-DEL", "derivable de créditos comunes"),
    ("E-049", "contributor (coros/voces) en MusicAlbum", "—", "Somos unos animales; Deltoya; ¿Dónde están mis amigos?", f"{S}/extremoduro/<disco>#album", "W-SUA · W-DEL · W-DEMA", "SongCredit sin persona: crédito con nombre libre"),
    ("E-055", "creator (artwork) en MusicAlbum", "—", "Tú en tu casa, nosotros en la hoguera (1990) [HIPÓTESIS]", f"{S}/extremoduro/tu-en-tu-casa-nosotros-en-la-hoguera#album", T("1:58:35"), "no existe: crédito de arte"),
    ("E-068", "creator en CreativeWork (VisualArtwork)", "—", "Mural de Robe y Manolo Chinato (Plasencia)", "pendiente (página del mural)", "PR-431", "no existe: obra nueva"),
    ("E-068", "creator en CreativeWork (VisualArtwork)", "—", "«El Descendimiento» (2025)", "sin página: nodo con nombre", "FORBES", "no existe"),
    ("E-068", "homeLocation / birthPlace", "—", "Plasencia («artista placentino»)", f"{S}/lugares/plasencia#place", "FORBES", "no existe: tabla de relaciones"),
    ("E-068", "about (del mural)", "subjectOf", "Robe; Manolo Chinato", f"{S}/personas/robe-iniesta#person · /personas/manolo-chinato#person", "PR-431", "no existe"),
]


def afirmable(fuentes: list[str]) -> bool:
    return any(not f.startswith("FONDO@") and f != "JC" for f in fuentes)


def esqueleto(p: dict) -> str:
    """Cuerpo mínimo para que las guardas lean los H2 y los hechos afirmables."""
    partes = [f"# {p['nombre']}"]
    for h in p["h2"]:
        partes.append(f"## {h}")
    partes += [h for h, f in p["hechos"] if afirmable(f)]
    partes.append("Robe Extremoduro Plasencia")
    return "\n\n".join(partes)


filas, registro = [], []
for p in MUESTRA:
    vol = VOL.get(p["id"]) or VOL.get("E-049/E-050" if p["id"] in ("E-049", "E-050") else "", {})
    tv = dv = None
    if p["title"]:
        body = esqueleto(p)
        tv = seo_style.title_verdict(p["title"], body_md=body, subject=p["nombre"], entity_type="person",
                                     target_keyword=p["kw"])
        dv = seo_style.desc_verdict(p["desc"], title=p["title"], body_md=body, entity_type="person")
    n_af = sum(afirmable(f) for _, f in p["hechos"])
    filas.append({
        "id": p["id"], "persona": p["nombre_completo"], "grupo": p["grupo"], "slug_propuesto": p["slug"],
        "hechos_afirmables": n_af, "hechos_solo_fondo": len(p["hechos"]) - n_af,
        "volumen_dataforseo": "; ".join(f"{k}={v['search_volume'] if v['search_volume'] is not None else 'n/d'}"
                                        for k, v in vol.items()),
        "kw_principal": p["kw"], "kw_secundarias": "; ".join(p["kw_sec"]),
        "title": p["title"], "title_len": len(p["title"]),
        "title_veredicto": ("" if tv is None else ("BLOQUEA: " + "; ".join(tv.motivos) if tv.motivos else "ok")
                            + ("" if tv is None or not tv.avisos else " · avisos: " + "; ".join(tv.avisos))),
        "description": p["desc"], "desc_len": len(p["desc"]),
        "desc_veredicto": ("" if dv is None else ("BLOQUEA: " + "; ".join(dv.motivos) if dv.motivos else "ok")
                           + ("" if dv is None or not dv.avisos else " · avisos: " + "; ".join(dv.avisos))),
        "h2": " | ".join(p["h2"]), "recomendacion": p["recomendacion"], "motivo": p["motivo"],
    })

with open(OUT / "personas_propuesta_muestra.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(filas[0]))
    w.writeheader()
    w.writerows(filas)
with open(OUT / "relaciones_muestra.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "propiedad_schema", "inversa", "destino", "id_destino", "evidencia", "estado_del_dato"])
    w.writerows(RELACIONES)
json.dump({"fuentes": FUENTES, "muestra": MUESTRA}, open(OUT / "muestra_evidencia.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
for r in filas:
    print(r["id"], r["persona"], "|", r["hechos_afirmables"], "afirmables |", r["recomendacion"])
    if r["title"]:
        print("   T", r["title_len"], r["title_veredicto"])
        print("   D", r["desc_len"], r["desc_veredicto"])
