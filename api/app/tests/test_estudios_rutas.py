"""Las rutas de los estudios, que no viven en la BD.

`guard_internal_links` resuelve cada enlace interno contra el catálogo, así que un
`/estudios/<slug>` le parecía inventado y lo DESENLAZABA en silencio: medido el
07-10-2026, el enlace del post al estudio desaparecía al republicar. `ESTUDIO_SLUGS`
lo arregla sin aflojar nada, porque el slug se sigue comprobando.

La lista está duplicada: el registro con títulos y fechas vive en
`web/lib/estudios.ts` y la guarda corre en el backend. Aquí se prueba el
comportamiento del resolver, que es lo que se puede probar: la imagen del api se
construye solo con `api/` y no ve `web/`. **Que las dos listas no divergan lo
comprueba el paso «estudios sincronizados» de `.github/workflows/tests.yml`**, que
corre en el runner con el repo entero delante. Si mueves una, mira la otra.
"""
from __future__ import annotations

import pytest

from app.services.url_resolver import ESTUDIO_SLUGS, Resolution, resolve_path


class _CatalogoVacio:
    """`resolve_path` no toca la BD para una ruta de estudio."""

    def section_entity(self, *_a, **_k):  # pragma: no cover - no debería llamarse
        raise AssertionError("una ruta de estudio no se busca en el catálogo")


@pytest.mark.parametrize("slug", sorted(ESTUDIO_SLUGS))
def test_el_estudio_publicado_resuelve(slug: str):
    res: Resolution = resolve_path(_CatalogoVacio(), f"/estudios/{slug}")
    assert res.status == "not_catalog", res
    assert res.canonical_path == f"/estudios/{slug}"


def test_el_indice_resuelve():
    assert resolve_path(_CatalogoVacio(), "/estudios").status == "not_catalog"


def test_un_estudio_inventado_sigue_cayendo():
    # El prefijo no basta: si no, el LLM podría colar cualquier /estudios/lo-que-sea.
    res = resolve_path(_CatalogoVacio(), "/estudios/la-verdad-sobre-robe")
    assert res.status == "not_found", res
