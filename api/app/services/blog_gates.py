"""La cascada de filtros del día de publicar, en seco: se sabe ANTES si una pieza pasa.

Plan del blog (18-11-2026). El aniversario de «Destrozares» se escribió y se juzgó a
las 08:00 del día en que tenía que salir, y murió ahí. Medido en los logs desde el
27-09: 25 descartes por rigor, 19 piezas a revisión y 4 publicadas en el cron. El
juicio tiene que pasar cuando la pieza se prepara, días antes, y tiene que ser la
cascada ENTERA (foco, rigor, citas, años, completitud, voz, hechos), no solo el juez.

`cascada_en_seco` no crea ningún Post ni toca la BD: recibe un cuerpo y dice qué filtro
lo frena y por qué. `materialize_proposals` sigue siendo quien publica.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from types import SimpleNamespace

logger = logging.getLogger(__name__)


@dataclass
class Juicio:
    pasa: bool
    bloquea: str | None = None          # foco | rigor | lyrics | facts | completeness | fuentes | material
    motivos: list[str] = field(default_factory=list)
    score: int | None = None
    cuerpo: str = ""                     # el cuerpo tras recortes y tensado
    # Motivos del juez que piden un DATO (se resuelven buscando material, no reescribiendo).
    faltan_datos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"pasa": self.pasa, "bloquea": self.bloquea, "motivos": self.motivos,
                "score": self.score, "faltan_datos": self.faltan_datos}


_PIDE_DATO = ("no da", "no identifica", "no menciona", "no indica", "falta", "faltan",
              "omite", "no incluye", "no aporta la fecha", "sin fecha")


def motivos_de_dato(motivos: list[str]) -> list[str]:
    """Los motivos del juez que reclaman un hecho ausente. Volver a pedírselo al
    redactor sin material nuevo le enseña a esquivar o a inventar: esos se resuelven
    buscando el dato. Los demás (repetición, relleno) sí son de reescritura."""
    return [m for m in motivos if any(k in m.lower() for k in _PIDE_DATO)]


_NOMBRE_COMPLETO = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)[ ]+([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)\b")


def _prefijo_comun(a: str, b: str) -> int:
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return i


def nombres_dudosos(db, cuerpo: str) -> list[tuple[str, str]]:
    """[(nombre del texto, persona de la casa)] cuando el apellido es de una sola persona
    de la BD y el nombre no coincide con el suyo (ni con su nombre artístico)."""
    import unicodedata

    from app.db.models import Person

    def n(x: str) -> str:
        x = unicodedata.normalize("NFKD", (x or "").lower())
        return " ".join("".join(c for c in x if not unicodedata.combining(c)).split())

    conocidos: set[str] = set()
    # apellido → [(nombre para mostrar, {nombres de pila conocidos})]
    por_apellido: dict[str, list[tuple[str, set[str]]]] = {}
    for stage, full in db.query(Person.stage_name, Person.full_name):
        for nombre in (stage, full):
            if nombre:
                conocidos.add(n(nombre))
        partes = n(full or stage or "").split()
        pilas = {x.split()[0] for x in (n(stage or ""), n(full or "")) if x}
        if len(partes) >= 2:
            apellidos = {partes[-1]} | ({partes[-2]} if len(partes) >= 3 else set())
            for ap in apellidos:            # «Rosendo Mercado Ruiz»: también el primero
                por_apellido.setdefault(ap, []).append((stage or full, pilas))
    out = []
    for m in _NOMBRE_COMPLETO.finditer(cuerpo or ""):
        completo, pila, apellido = n(m.group(0)), n(m.group(1)), n(m.group(2))
        if completo in conocidos:
            continue
        dueños = por_apellido.get(apellido) or []
        if len(dueños) != 1:
            continue
        mostrar, pilas = dueños[0]
        # La errata de transcripción empieza igual y se desvía pronto (Álvaro / Alber: «al»).
        # Un diminutivo comparte más (Manolo / Manolillo) y un familiar suele llamarse
        # distinto (Iñigo y Fermín Muguruza): esos no se marcan (medido sobre 382 textos).
        cercanía = max((_prefijo_comun(pila, p) for p in pilas), default=0)
        if pila not in pilas and 2 <= cercanía <= 3:
            out.append((m.group(0), mostrar))
    return list(dict.fromkeys(out))


def cascada_en_seco(db, *, kind: str, subject: str, title: str, body_md: str,
                    hard_facts: str = "", tipo_pieza: str | None = None,
                    usar_web: bool = True, material_propio: str = "") -> Juicio:
    from app.services.editorial_review import review
    from app.services.focus_check import check_focus
    from app.services.piece_checklist import liston

    lst = liston(tipo_pieza or kind, hard_facts)
    cuerpo = body_md or ""

    # 1. Foco: recorta lo desviado, pero lo que pide el encargo no es desviación.
    f = check_focus(cuerpo, subject, focus=lst.enfoque() if lst else "")
    if not f.ok:
        if f.trimmed_body_md:
            cuerpo = f.trimmed_body_md
        else:
            return Juicio(False, "foco", [f"deriva sin recorte limpio (foco {f.score})"],
                          cuerpo=cuerpo)

    # 2. Rigor, con los hechos duros delante: así distingue «no lo escribió» de «no existe».
    # El juez tiene varianza medida (58 y 72 sobre el MISMO texto): se decide por mayoría
    # de tres tiradas (dos si coinciden). Una sola tirada dio «pasa» a un texto que
    # después se rechazó tres de tres veces (asesor, 18-11-2026).
    def _tirada():
        return review(cuerpo, kind=kind, subject=subject, material=hard_facts or None,
                      no_consta=lst.para_el_juez() if lst else "")

    tiradas = [_tirada(), _tirada()]
    if (tiradas[0].verdict == "reject") != (tiradas[1].verdict == "reject"):
        tiradas.append(_tirada())
    rechazos = [t for t in tiradas if t.verdict == "reject"]
    aceptadas = [t for t in tiradas if t.verdict != "reject"]
    v = (min(rechazos, key=lambda t: t.score) if len(rechazos) > len(aceptadas)
         else max(aceptadas, key=lambda t: t.score))
    rechazo_rigor = None
    if v.verdict == "reject":
        # No se corta aquí: «para tu lectura» exige saber que el resto de filtros pasa de
        # verdad (asesor, 18-11-2026). Si otro filtro frena, manda ese.
        rechazo_rigor = Juicio(False, "rigor", v.reasons, v.score, cuerpo,
                               faltan_datos=motivos_de_dato(v.reasons))
    elif v.verdict == "revise" and v.tightened_body_md:
        cuerpo = v.tightened_body_md

    # 3. Deterministas del día D: citas de letra, años de disco, completitud.
    from app.services.publishing import gates_deterministas
    # El tipo de pieza, no el kind: «cómo se hizo un disco» es un evergreen por kind y una
    # pieza de una sola obra para la completitud.
    falso_post = SimpleNamespace(id=None, body_md=cuerpo, kind=tipo_pieza or kind, title=title,
                                 target_keyword=subject)
    det = gates_deterministas(db, falso_post)
    if det:
        return Juicio(False, det[0], [det[1]], v.score, cuerpo)

    # 4. La voz es nuestra: nombrar a un medio o a un analista va a revisión.
    from app.services.source_guard import fuentes_nombradas, nombres_de_fuentes
    fuentes = fuentes_nombradas(cuerpo, nombres_de_fuentes(db))
    if fuentes:
        return Juicio(False, "fuentes", [f"nombra «{f[:80]}»" for f, _ in fuentes[:3]],
                      v.score, cuerpo)

    # 4b. Nombres con errata de transcripción: «Álvaro Fuentes» por Alber Fuentes salió en
    #     «Cómo se hizo Mayéutica» (18-11-2026). Si el apellido es de UNA sola persona de la
    #     casa y el nombre no es el suyo, se para: es una errata o es otra persona.
    dudosos = nombres_dudosos(db, cuerpo)
    if dudosos:
        return Juicio(False, "facts", [f"nombre dudoso: «{n}» (¿{c}?)" for n, c in dudosos[:3]],
                      v.score, cuerpo)

    # 5. Hechos contra la BD y la web (lo dudoso va a revisión).
    if usar_web:
        from app.services.fact_check import check_body
        rep = check_body(db, cuerpo, use_web=True,
                         material=f"{hard_facts}\n\n{material_propio}".strip())
        if rep.extraccion_fallida:
            # Sin afirmaciones extraídas no hay comprobación: no es «limpio».
            return Juicio(False, "facts", ["no se pudieron extraer los hechos para comprobarlos"],
                          v.score, cuerpo)
        if rep.to_review:
            return Juicio(False, "facts",
                          [f"{x.claim.type}: {x.claim.subject}" for x in rep.to_review[:5]],
                          v.score, cuerpo)

    return rechazo_rigor or Juicio(True, None, v.reasons, v.score, cuerpo)
