"""Auto-arreglo de una errata concreta desde la cola admin (botón «Arreglar»).

El barrido nocturno del MCV corre sobre los YAML curados; esto es su hermano
puntual: coges UNA errata de la cola y le vuelves a pasar el Motor de Consenso
AHORA, con las fuentes de ahora. Sirve para dos cosas muy prácticas:

  1. La errata ya está resuelta de facto (la letra se corrigió, el crédito se
     insertó, el disco que faltaba ya está ingerido) → se cierra sola.
  2. El consenso, que la primera vez no llegó al umbral, ahora sí llega (una
     fuente que estaba caída responde) → se aplica y se cierra.

Y cuando NO puede, lo dice con nombre y apellidos en vez de quedarse mudo: qué
fuentes respondieron, qué veredicto salió, con qué confianza y qué falta para
poder cerrarla. Las reglas de integridad no se relajan: se reutilizan
`decide_fan_correction` y los mismos verificadores por eje, así que aquí no se
aplica nada que el barrido no aplicaría.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import Album, Artist, ErrataReport, Song, SongCredit
from app.services import consensus as mcv

logger = logging.getLogger(__name__)


@dataclass
class FixOutcome:
    """Resultado de intentar arreglar una errata."""

    action: str                       # applied | already_ok | no_consensus | not_supported | error
    message: str                      # frase para el admin
    applied: bool = False             # ¿se tocó el dato?
    closed: bool = False              # ¿se cerró la errata?
    detail: str | None = None         # traza técnica breve
    verdict: str | None = None
    confidence: float | None = None
    sources: list[str] = field(default_factory=list)
    # Canciones cuyos embeddings hay que refrescar (alta de disco). Interno.
    propagate_song_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "message": self.message,
            "applied": self.applied,
            "closed": self.closed,
            "detail": self.detail,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "sources": self.sources,
        }


def _close(errata: ErrataReport, note: str, *, status: str = "applied") -> None:
    errata.status = status
    errata.resolution_note = note[:2000]
    errata.resolved_at = datetime.now(timezone.utc)


def _supporting_sources(result) -> list[str]:
    return [f"{s.name} (T{s.tier})" for s in result.sources if s.stance == "supports"]


# --------------------------------------------------------------------------- #
# Eje A · letras
# --------------------------------------------------------------------------- #
def _fix_lyrics(db, errata: ErrataReport) -> FixOutcome:
    from app.services import lyric_fetchers
    from app.services.lyric_guard import normalize
    from scripts.verify import lyrics_consensus as lc

    song = db.get(Song, errata.target_id) if errata.target_id else None
    wrong, right = errata.reported_wrong, errata.suggested_right
    if not song:
        return FixOutcome("not_supported", "La errata no apunta a ninguna canción de la BD.")
    if not (wrong and right):
        return FixOutcome(
            "not_supported",
            "Falta el verso mal o el verso correcto: sin hipótesis que verificar.",
        )

    # ¿Ya está corregido en BD? (el barrido pudo aplicarlo tras abrir la errata).
    # OJO: se compara LÍNEA a LÍNEA con el criterio de tokens de lyrics_consensus,
    # que distingue cambios de palabra («llega»/«lleva»). Con un solapamiento difuso
    # sobre la letra entera, esas dos daban ≥0.95 y la errata se cerraba en falso
    # dejando el verso mal — justo lo que no puede pasar.
    if any(lc._line_equivalent(line, right) for line in (song.lyrics_clean or "").split("\n")):
        _close(errata, f"Ya corregido en BD: la letra de «{song.title}» dice el verso bueno.")
        return FixOutcome(
            "already_ok",
            f"Ya estaba arreglado: la letra de «{song.title}» dice el verso correcto. Errata cerrada.",
            closed=True,
        )

    external = lyric_fetchers.fetch_all(song.title, lc._artist_name(db, song))
    result = lc.verify_line(db, song, wrong=wrong, right=right, external=external)
    action = mcv.decide_fan_correction(result, fan_value=right)
    verif = mcv.record_verification(
        db, claim_kind="lyric_line",
        claim_key=f"song:{song.id}:line:{normalize(wrong)[:60]}",
        result=result, song_id=song.id, applied=(action == "auto_apply"),
    )
    db.flush()
    responded = list(external.keys()) or ["ninguna"]

    if action != "auto_apply":
        return FixOutcome(
            "no_consensus",
            "El consenso sigue sin dar para aplicarlo solo: hace falta tu criterio.",
            detail=(
                f"Fuentes externas que respondieron: {', '.join(responded)}. "
                f"{result.rationale}"
            ),
            verdict=result.verdict, confidence=result.confidence,
            sources=_supporting_sources(result),
        )

    fixed = result.correct_value or right
    ok = lc.apply_line_fix(db, song, wrong, fixed, result.confidence)
    if not ok:
        return FixOutcome(
            "no_consensus",
            "El consenso lo respalda, pero el verso malo ya no aparece en la letra guardada.",
            detail=f"Buscaba «{wrong}» en «{song.title}» y no casa con ninguna línea.",
            verdict=result.verdict, confidence=result.confidence,
            sources=_supporting_sources(result),
        )
    errata.verification_id = verif.id
    _close(errata, f"Aplicado por consenso (conf {result.confidence:.2f}): «{wrong}» → «{fixed}».")
    return FixOutcome(
        "applied",
        f"Corregido: «{wrong}» → «{fixed}».",
        applied=True, closed=True,
        detail=f"Fuentes externas que respondieron: {', '.join(responded)}.",
        verdict=result.verdict, confidence=result.confidence,
        sources=_supporting_sources(result),
    )


# --------------------------------------------------------------------------- #
# Eje B · autoría
# --------------------------------------------------------------------------- #
def _author_from_suggestion(suggested: str) -> str:
    """«Manolo Chinato (autoría)» → «Manolo Chinato»."""
    name = (suggested or "").strip()
    if "(" in name:
        name = name.split("(", 1)[0]
    return name.strip(" ·-—")


def _fix_authorship(db, errata: ErrataReport) -> FixOutcome:
    from app.services import curated_overrides as co
    from app.services.lyric_guard import best_ratio, normalize
    from scripts.verify import authorship_consensus as ac

    song = db.get(Song, errata.target_id) if errata.target_id else None
    author = _author_from_suggestion(errata.suggested_right or "")
    if not song:
        return FixOutcome("not_supported", "La errata no apunta a ninguna canción de la BD.")
    if not author:
        return FixOutcome("not_supported", "La errata no dice de quién es la autoría.")

    # ¿El crédito ya existe? Entonces esto ya se aplicó y la errata sobra.
    existing = db.execute(
        select(SongCredit).where(SongCredit.song_id == song.id)
    ).scalars().all()
    if any(best_ratio(normalize(author), normalize(c.credited_name or "")) >= 0.9 for c in existing):
        _close(errata, f"Ya aplicado: «{song.title}» acredita a {author} en song_credits.")
        return FixOutcome(
            "already_ok",
            f"Ya estaba arreglado: «{song.title}» acredita a {author}. Errata cerrada.",
            closed=True,
        )

    # Los créditos concretos (roles) salen del YAML curado; sin entrada no
    # inventamos roles: es dato editorial, no se rellena a ojo.
    entry = None
    for cand in co.song_credits():
        if best_ratio(normalize(cand.get("song_title") or ""), normalize(song.title)) >= 0.75:
            entry = cand
            break
    if not entry:
        return FixOutcome(
            "not_supported",
            "No hay entrada curada para esta canción: no puedo inventarme los roles del crédito.",
            detail=(
                f"Añade «{song.title}» a data/song_credits.yaml (role + name + person_slug) "
                "y vuelve a darle a Arreglar."
            ),
        )

    credits = entry.get("credits") or []
    key = next((c for c in credits if c.get("role") in ("poema_original", "letra", "adaptacion")), None)
    if not key:
        return FixOutcome(
            "not_supported",
            "La entrada curada no tiene rol autoral (poema_original/letra/adaptacion).",
        )

    result = ac.verify_credit(db, song, key["name"], key["role"])
    action = mcv.decide_fan_correction(result, fan_value=key["name"])
    verif = mcv.record_verification(
        db, claim_kind="song_authorship",
        claim_key=f"song:{song.id}:authorship:{normalize(key['name'])}",
        result=result, song_id=song.id, applied=(action == "auto_apply"),
    )
    db.flush()

    if action != "auto_apply":
        return FixOutcome(
            "no_consensus",
            "Sin corroboración externa suficiente para atribuir la autoría solo.",
            detail=result.rationale,
            verdict=result.verdict, confidence=result.confidence,
            sources=_supporting_sources(result),
        )

    n = ac.apply_credits(db, song, credits, result.confidence)
    errata.verification_id = verif.id
    _close(errata, f"Créditos aplicados por consenso (conf {result.confidence:.2f}): {n} insertado(s).")
    return FixOutcome(
        "applied",
        f"Autoría aplicada: {n} crédito(s) en «{song.title}» ({key['name']}).",
        applied=True, closed=True,
        verdict=result.verdict, confidence=result.confidence,
        sources=_supporting_sources(result),
    )


# --------------------------------------------------------------------------- #
# Eje C · catálogo
# --------------------------------------------------------------------------- #
def _expected_album_title(db, errata: ErrataReport, song: Song) -> str | None:
    """Título del disco que falta: primero el YAML curado, si no el texto de la
    errata («… disco de estudio: «Tú en tu casa…» (1990)»)."""
    from app.services import curated_overrides as co
    from app.services.lyric_guard import best_ratio, normalize

    bare = _bare_title(song.title)
    for entry in co.canonical_tracklists():
        if best_ratio(normalize(entry.get("song_title") or ""), normalize(bare)) >= 0.8:
            if entry.get("original_album"):
                return str(entry["original_album"])
    m = re.search(r"«([^»]+)»", errata.suggested_right or "")
    return m.group(1) if m else None


def _bare_title(title: str) -> str:
    """«Amor castúo (En Directo)» → «Amor castúo»."""
    return re.sub(r"[\(\[].*?[\)\]]", "", title or "").strip()


def _ingest_missing_album(db, errata: ErrataReport, song: Song, slug: str) -> FixOutcome:
    """Da de alta el disco ausente, de punta a punta, si la certeza es total."""
    from app.services import catalog_ingest as ci

    album_title = _expected_album_title(db, errata, song)
    if not album_title:
        return FixOutcome(
            "not_supported",
            "No sé qué disco falta: ni el YAML curado ni la errata dicen su título.",
        )

    current_album = db.get(Album, song.album_id)
    artist = db.get(Artist, current_album.artist_id) if current_album else None
    if not artist:
        return FixOutcome("not_supported", "No puedo resolver el artista de la canción.")

    found = ci.find_release_group(album_title, artist.name)
    if found is not None:
        found = ci.fetch_tracklist(found)
    try:
        ev = ci.certify(
            found,
            expected_title=album_title,
            expected_artist=artist.name,
            expected_year=song.original_year,
            must_contain=_bare_title(song.title),
        )
    except ci.AlbumNotCertain as exc:
        return FixOutcome(
            "not_supported",
            f"No lo doy de alta solo: {exc}",
            detail=(
                "Si aun así quieres el disco, añádelo a data/discography.yaml, corre "
                f"`python -m scripts.seed_catalog` y `python -m scripts.ingest --album-slug {slug}`."
            ),
        )

    result = ci.build_consensus(ev, expected_year=song.original_year)
    if mcv.decide(result) != "auto_apply":
        return FixOutcome(
            "no_consensus",
            "MusicBrainz lo da, pero el consenso no llega al umbral para crearlo solo.",
            detail=result.rationale,
            verdict=result.verdict, confidence=result.confidence,
            sources=_supporting_sources(result),
        )

    summary = ci.create_album(db, ev, artist_id=artist.id, slug=slug, kind="studio")
    relinked = ci.link_original_versions(db, db.get(Album, summary["album_id"]), artist_id=artist.id)
    verif = mcv.record_verification(
        db, claim_kind="album_created", claim_key=f"album:{slug}",
        result=result, song_id=song.id, applied=True,
    )
    db.flush()
    errata.verification_id = verif.id
    _close(
        errata,
        f"Disco dado de alta por consenso (MusicBrainz, conf {result.confidence:.2f}): "
        f"«{ev.title}» ({ev.year}), {summary['songs_created']} canciones, "
        f"{summary['songs_with_lyrics']} con letra.",
    )
    new_song_ids = [
        s.id for s in db.execute(
            select(Song).where(Song.album_id == summary["album_id"])
        ).scalars() if s.lyrics_clean
    ]
    sin_letra = summary["songs_created"] - summary["songs_with_lyrics"]
    # Las fichas (álbum + canciones) tardan ~2 min cada una: van desatendidas, o el
    # listado de discografía enlazaría a 404 mientras tanto.
    filling = ci.schedule_content_fill(slug)
    minutos = (summary["songs_created"] + 1) * 2
    return FixOutcome(
        "applied",
        f"Disco dado de alta: «{ev.title}» ({ev.year}) con {summary['songs_created']} "
        f"canciones ({summary['songs_with_lyrics']} con letra"
        + (f", {sin_letra} sin letra disponible" if sin_letra else "")
        + f"). {relinked} versión(es) enlazada(s) a su disco original."
        + (f" Generando sus fichas en segundo plano (~{minutos} min)." if filling
           else " OJO: no arrancó la generación de fichas; corre "
                f"`python -m scripts.seo.fill_missing_content --album-slug {slug}`."),
        applied=True, closed=True,
        detail=(
            "Versiónalo en data/discography.yaml para que el seed lo reproduzca:\n"
            + ci.yaml_snippet(ev, slug)
        ),
        verdict=result.verdict, confidence=result.confidence,
        sources=_supporting_sources(result),
        propagate_song_ids=new_song_ids,
    )


def _fix_catalog(db, errata: ErrataReport) -> FixOutcome:
    """Las erratas de catálogo que abre el barrido son HUECOS DE DATOS: falta el
    disco de estudio donde la canción apareció por primera vez. Si la certeza es
    total (ver `catalog_ingest`), se da de alta el disco entero; si no, se dice
    qué falta y no se toca nada."""
    song = db.get(Song, errata.target_id) if errata.target_id else None
    if not song:
        return FixOutcome("not_supported", "La errata no apunta a ninguna canción de la BD.")

    slug = song.original_album_slug
    if not slug:
        return FixOutcome(
            "not_supported",
            "La canción no tiene disco original marcado: el consenso de catálogo no llegó a fijarlo.",
            detail="Corre `python -m scripts.verify.catalog_consensus --pending --apply`.",
        )

    album = db.execute(select(Album).where(Album.slug == slug)).scalar_one_or_none()
    if album is None:
        return _ingest_missing_album(db, errata, song, slug)

    # El disco ya está: ¿hay versión de estudio de la canción dentro?
    studio = db.execute(
        select(Song).where(Song.album_id == album.id)
    ).scalars().all()
    if album.kind == "studio" and studio:
        _close(
            errata,
            f"Hueco tapado: «{album.title}» ({album.year}) está en el catálogo con "
            f"{len(studio)} canción(es).",
        )
        return FixOutcome(
            "applied",
            f"Cerrada: «{album.title}» ({album.year}) ya está en el catálogo con {len(studio)} canción(es).",
            closed=True,
        )
    return FixOutcome(
        "not_supported",
        f"El disco «{album.title}» existe pero está vacío o no es de estudio (kind={album.kind}).",
        detail=f"Ingiere sus letras: `python -m scripts.ingest --album-slug {album.slug}`.",
    )


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
def _fix_image(db, errata: ErrataReport) -> FixOutcome:
    """Errata de imagen: la abre `audit_images` cuando retira una foto que nadie
    acredita. El arreglo no es automático (hay que encontrar una foto cuya fuente
    diga que es esa entidad), pero sí se comprueba si ya se repuso algo válido."""
    from app.services import image_guard

    # field = "image:band/rebrote"
    ref = (errata.field or "").removeprefix("image:")
    kind, _, slug = ref.partition("/")
    from scripts.seo.audit_images import TARGETS

    target = TARGETS.get(kind)
    if not target or not slug:
        return FixOutcome("not_supported", "No sé a qué imagen se refiere esta errata.")

    row = db.execute(select(target.model).where(target.model.slug == slug)).scalar_one_or_none()
    if row is None:
        return FixOutcome("not_supported", f"Ya no existe {kind}/{slug}.")

    url = getattr(row, target.url_field, None)
    if not url:
        return FixOutcome(
            "no_consensus",
            f"«{slug}» sigue sin foto. Ponle una cuya fuente acredite que es esta "
            "entidad (Commons con categoría propia) o arte propio marcado como ilustración.",
        )

    nombres = [str(getattr(row, nf)) for nf in target.name_fields if getattr(row, nf, None)]
    verdict = image_guard.verify_provenance(
        entity_name=nombres[0] if nombres else slug,
        aliases=nombres[1:],
        image_url=url,
        source_url=getattr(row, target.source_field, None) if target.source_field else None,
        attribution=getattr(row, target.attr_field, None) if target.attr_field else None,
        license_=getattr(row, target.lic_field, None) if target.lic_field else None,
    )
    if not verdict.publishable:
        # Pulsar «Arreglar» ES la decisión humana que la auditoría no se permite
        # tomar sola: aquí sí se retira, porque lo pide una persona mirando el caso.
        from sqlalchemy import update

        db.execute(update(target.model).where(target.model.id == row.id)
                   .values(**{target.url_field: None}))
        _close(errata, f"Foto retirada a petición del admin: {verdict.reason}")
        return FixOutcome(
            "applied",
            f"Foto retirada de «{slug}»: {verdict.reason} Mejor sin foto que con la de otro.",
            applied=True, closed=True,
            detail=" · ".join(verdict.evidence) or None,
        )
    if image_guard.must_rehost(url):
        return FixOutcome(
            "no_consensus",
            "La foto está acreditada pero sigue alojada fuera: se rompería con el 429.",
            detail="Corre `python -m scripts.seo.audit_images --fix`.",
        )
    _close(errata, f"Foto repuesta y acreditada: {verdict.reason}")
    return FixOutcome(
        "applied", f"Cerrada: la foto de «{slug}» ya está acreditada y alojada por nosotros.",
        closed=True, detail=" · ".join(verdict.evidence) or None,
    )


def _fix_internal_url(db, errata: ErrataReport) -> FixOutcome:
    """Errata de enlace interno: la abre `audit_urls` cuando una ruta del site no
    lleva a lo que dice.

    Se vuelve a resolver con los datos de AHORA, y eso cierra sola la mayoría:
    muchos enlaces «fantasma» dejaron de serlo cuando la ficha que faltaba se dio
    de alta (a `/extremoduro/tu-en-tu-casa-nosotros-en-la-hoguera` le pasó justo
    eso). Si sigue rota y no hay destino que proponer, se desenlaza — y ese es el
    paso que la auditoría no da sola: pulsar «Arreglar» ES la decisión humana.
    """
    from app.db.models import Post, SeoContent
    from app.services import url_resolver as ur

    # field = "url:link_cross:seo:/extremoduro/pedra" (las rutas no llevan «:»)
    trozos = (errata.field or "").split(":", 3)
    if len(trozos) != 4 or trozos[0] != "url":
        return FixOutcome("not_supported", "No sé a qué enlace se refiere esta errata.")
    _, check, origen, ruta = trozos

    cat = ur.DbCatalog(db)
    res = ur.resolve_path(cat, ruta)

    if origen not in ("seo", "post"):
        # No sale de un cuerpo: es un aviso sobre el catálogo, el sitemap o lo que
        # Google indexó. Se cierra sola si el motivo ya no se da.
        if res.is_ok and check != "dup_entity_slug":
            _close(errata, f"«{ruta}» ya resuelve bien.")
            return FixOutcome(
                "applied", f"Cerrada: «{ruta}» ya lleva a donde debe.", closed=True,
            )
        return FixOutcome(
            "no_consensus",
            f"«{ruta}» sigue sin cuadrar ({res.reason}). Esto no se arregla "
            "reescribiendo un enlace: hay que tocar el catálogo.",
        )

    if res.is_ok:
        _close(errata, f"«{ruta}» ya resuelve bien; el enlace no estaba roto.")
        return FixOutcome(
            "applied", f"Cerrada: «{ruta}» ya existe y lleva a lo que dice.", closed=True,
        )

    fila = db.get(SeoContent if origen == "seo" else Post, errata.target_id)
    if fila is None:
        return FixOutcome("not_supported", "Ya no existe el contenido que lo enlazaba.")

    if res.status == "redirect" and res.canonical_path:
        nuevo = ur._reenlazar(fila.body_md, ruta, res.canonical_path)
        if nuevo == fila.body_md:
            _close(errata, f"El enlace a «{ruta}» ya no está en el cuerpo.")
            return FixOutcome(
                "applied", f"Cerrada: «{ruta}» ya no se enlaza ahí.", closed=True,
            )
        fila.body_md = nuevo
        _close(errata, f"Enlace reapuntado: {ruta} → {res.canonical_path}")
        return FixOutcome(
            "applied",
            f"Enlace corregido: «{ruta}» ahora apunta a «{res.canonical_path}».",
            applied=True, closed=True,
        )

    nuevo = ur._desenlazar(fila.body_md, ruta)
    if nuevo == fila.body_md:
        _close(errata, f"El enlace a «{ruta}» ya no está en el cuerpo.")
        return FixOutcome(
            "applied", f"Cerrada: «{ruta}» ya no se enlaza ahí.", closed=True,
        )
    fila.body_md = nuevo
    _close(errata, f"Enlace fantasma desenlazado a petición del admin: {ruta}")
    return FixOutcome(
        "applied",
        f"«{ruta}» no lleva a ningún sitio ({res.reason}): se ha quitado el enlace "
        "y el texto se queda como estaba.",
        applied=True, closed=True,
    )


_HANDLERS = {
    "song_lyrics": _fix_lyrics,
    "authorship": _fix_authorship,
    "catalog": _fix_catalog,
    "image": _fix_image,
    "internal_url": _fix_internal_url,
}


def try_fix(db, errata: ErrataReport) -> FixOutcome:
    """Intenta resolver la errata con el Motor de Consenso. Nunca lanza: si algo
    revienta, devuelve un outcome de error (la cola no se rompe por una errata)."""
    if errata.status in ("applied", "rejected"):
        return FixOutcome("already_ok", f"Esta errata ya está {errata.status}.", closed=True)

    handler = _HANDLERS.get(errata.target_type)
    if handler is None:
        return FixOutcome(
            "not_supported",
            f"Las erratas de tipo «{errata.target_type}» son texto editorial: no hay dato "
            "que verificar contra fuentes. Corrige el contenido y márcala aplicada.",
        )
    try:
        outcome = handler(db, errata)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[errata_fix] errata %s reventó", errata.id)
        db.rollback()
        return FixOutcome("error", "Reventó al intentar arreglarla.", detail=str(exc)[:300])

    db.commit()  # la traza de VerificationRecord se guarda aunque no se aplique
    if outcome.applied:
        from app.services import freshness

        if errata.target_type == "song_lyrics":
            freshness.propagate(db, "lyric", song_id=errata.target_id)
        elif errata.target_type == "authorship":
            freshness.propagate(db, "authorship", song_id=errata.target_id)
        elif outcome.propagate_song_ids:
            # Disco nuevo: vectoriza sus letras y marca el grafo sucio (entidades
            # y aristas nuevas las repone build_graph en el barrido).
            for sid in outcome.propagate_song_ids:
                freshness.propagate(db, "lyric", song_id=sid)
            freshness.mark_graph_dirty()
    return outcome
