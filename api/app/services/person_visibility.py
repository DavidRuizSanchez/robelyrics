"""Una persona sin ficha publicada no existe para el público.

Hasta el 10-11-2026, una fila nueva en `persons` era al instante una página
indexable (`/personas/<slug>` respondía 200 con solo los datos de Wikidata),
entraba en el hub `/personas`, en los miembros del grupo, en el buscador y en el
autolink de todos los cuerpos. Dar de alta a alguien para preparar su ficha
publicaba una página pobre sin que nadie lo decidiera.

La regla es la misma que ya aplicaba `url_resolver._publicado` a los enlaces: la
persona se ve cuando tiene `seo_content` publicado. El día del cambio las 48
personas de prod lo tenían (medido el 10-11-2026), así que no cambia nada de lo
que ya se ve: solo afecta a las altas nuevas mientras su ficha es un borrador.

Todos los caminos que enseñan o enlazan una persona tiran de aquí, para que no
haya que acordarse de siete sitios.
"""
from __future__ import annotations

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session


def persona_publicada():
    """Cláusula SQL: la `Person` de la consulta tiene ficha publicada."""
    from app.db.models import Person, SeoContent

    return exists().where(and_(
        SeoContent.entity_type == "person",
        SeoContent.entity_id == Person.id,
        SeoContent.published.is_(True),
    ))


def ids_publicadas(db: Session) -> set[int]:
    """Ids de las personas con ficha publicada (para filtrar en Python)."""
    from app.db.models import SeoContent

    return set(db.execute(
        select(SeoContent.entity_id).where(
            SeoContent.entity_type == "person",
            SeoContent.published.is_(True),
        )
    ).scalars())
