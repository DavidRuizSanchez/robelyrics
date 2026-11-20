"""Enfriamiento de metadatos: una página cambiada hace poco no se vuelve a tocar.

Del 11 al 17-11-2026 se cambió el title de 339 páginas, y 178 lo cambiaron dos o tres
veces en una semana («Golfa», cuatro en seis días) porque cuatro caminos escribían a la
vez sin verse: titles humanos, su v2, los headings y las oportunidades `meta`. Varias
perdieron su consulta principal el día exacto del cambio («La vereda de la puerta de
atrás», de unas 90 impresiones al día a unas 10). Cubrir una consulta con las palabras
del title no impide que Google reevalúe la página, y cada cambio reinicia esa
evaluación.

Regla (David, 20-11-2026): ningún camino que escriba title, description, H1 o headings
toca una página que los cambió hace menos de 28 días. Aquí está la única respuesta a
«¿se puede tocar?», y sale de dos sitios:

- `page_changes`: lo que el monitor diario vio cambiar en lo SERVIDO. Es la fuente
  buena, pero llega con hasta un día de retraso.
- `content_revisions`: la copia que deja cada camino justo antes de pisar. Cubre ese
  día de retraso: si la página de hoy no tiene los metadatos de una copia reciente,
  alguien los cambió después de hacerla.

La segunda mitad del mismo incidente: `ranking_guard` daba por cubiertas las consultas
de un volcado de GSC que acababa el 02-10, y las de «La vereda» nacieron el 03-11. Un
volcado viejo no protege nada (`volcado_caducado`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

DIAS_ENFRIAMIENTO = 28
CAMPOS = ("title", "description", "h1", "headings")
# El volcado es semanal y GSC va unos tres días por detrás: con 14 cabe una semana
# perdida sin dar por bueno un volcado de hace un mes.
MAX_DIAS_VOLCADO = 14
_HEADING = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.M)


@dataclass(frozen=True)
class Enfriamiento:
    path: str
    campo: str            # title | description | h1 | headings
    cambiado: datetime
    dias: int = DIAS_ENFRIAMIENTO

    @property
    def hasta(self) -> datetime:
        return self.cambiado + timedelta(days=self.dias)

    def motivo(self) -> str:
        return (f"en enfriamiento: {self.campo} cambiado el {self.cambiado:%d-%m-%Y}, "
                f"no se toca hasta el {self.hasta:%d-%m-%Y}")


def _ruta(path: str) -> str:
    return "/" + (path or "").strip().strip("/")


def _headings(body_md: str | None) -> list[str]:
    return [h.strip() for h in _HEADING.findall(body_md or "")]


def campo_distinto(revision, fila) -> str | None:
    """El primer metadato en que la página de hoy difiere de una copia anterior."""
    if (revision.meta_title or "") != (getattr(fila, "meta_title", None) or ""):
        return "title"
    if (revision.meta_description or "") != (getattr(fila, "meta_description", None) or ""):
        return "description"
    # En un post el H1 es su título; en una ficha, el campo `h1`.
    h1_hoy = getattr(fila, "h1", None) or getattr(fila, "title", None)
    if revision.h1 is not None and (revision.h1 or "") != (h1_hoy or ""):
        return "h1"
    if _headings(revision.body_md) != _headings(getattr(fila, "body_md", None)):
        return "headings"
    return None


def rutas_en_enfriamiento(db, dias: int = DIAS_ENFRIAMIENTO, *, ahora: datetime | None = None,
                          path: str | None = None) -> dict[str, Enfriamiento]:
    """Las páginas que no se pueden tocar, con su último cambio. Con `path`, solo esa."""
    from app.db.models import ContentRevision, PageChange, Post, SeoContent

    ahora = ahora or datetime.now(UTC)
    limite = ahora - timedelta(days=dias)
    out: dict[str, Enfriamiento] = {}

    def anotar(ruta: str, campo: str, cuando: datetime) -> None:
        if cuando.tzinfo is None:
            cuando = cuando.replace(tzinfo=UTC)
        previo = out.get(ruta)
        if previo is None or cuando > previo.cambiado:
            out[ruta] = Enfriamiento(ruta, campo, cuando, dias)

    cambios = db.query(PageChange.path, PageChange.campo, PageChange.detected_at).filter(
        PageChange.campo.in_(CAMPOS), PageChange.detected_at >= limite)
    revisiones = db.query(ContentRevision).filter(ContentRevision.created_at >= limite)
    if path is not None:
        cambios = cambios.filter(PageChange.path.in_({_ruta(path), _ruta(path) + "/"}))
        revisiones = revisiones.filter(
            ContentRevision.path.in_({_ruta(path), _ruta(path) + "/"}))
    for ruta, campo, cuando in cambios.all():
        anotar(_ruta(ruta), campo, cuando)
    filas: dict[tuple[str, int], object] = {}
    for rev in revisiones.all():
        clave = (rev.target_kind, rev.target_id)
        if clave not in filas:
            filas[clave] = db.get(Post if rev.target_kind == "post" else SeoContent,
                                  rev.target_id)
        campo = campo_distinto(rev, filas[clave]) if filas[clave] is not None else None
        if campo:
            anotar(_ruta(rev.path), campo, rev.created_at)
    return out


def en_enfriamiento(db, path: str, dias: int = DIAS_ENFRIAMIENTO, *,
                    ahora: datetime | None = None) -> Enfriamiento | None:
    """¿Cambió esta página su title, description, H1 o headings hace menos de `dias`?"""
    return rutas_en_enfriamiento(db, dias, ahora=ahora, path=path).get(_ruta(path))


def volcado_caducado(periodo: str | None, *, hoy: date | None = None,
                     max_dias: int = MAX_DIAS_VOLCADO) -> str | None:
    """El motivo por el que el volcado de GSC no vale para proteger consultas, o None.

    `periodo` es el de `content_placement.load_gsc_pages` («2026-08-21..2026-11-13»).
    Sin fecha de fin no se sabe de cuándo es, y eso también es no valer.
    """
    fin = (periodo or "").split("..")[-1].strip()
    try:
        hasta = date.fromisoformat(fin)
    except ValueError:
        return "el volcado de GSC no dice hasta qué día llega"
    hoy = hoy or datetime.now(UTC).date()
    dias = (hoy - hasta).days
    if dias > max_dias:
        return (f"el volcado de GSC acaba el {hasta:%d-%m-%Y} (hace {dias} días): las "
                "consultas nuevas no estarían protegidas. Hay que traer uno reciente "
                "(`gsc_fetch_page_queries`)")
    return None
