"""Corrige los enlaces internos restantes que el audit no podía resolver
automáticamente (resolver tolerante no encuentra match único).

Fixes con destino conocido en BD:
  /extremoduro/agila/abre-el-pecho-y-registra → /extremoduro/agila/abreme-el-pecho-y-registra
  /extremoduro/iros-todos-a-tomar-por-culo/bri-bri-bli-bli-en-directo → ...-en-el-mas-sucio-rincon-...-en-directo
  /robe/mayeutica/despues-de-la-catarsis → /robe/mayeutica/primer-movimiento-despues-de-la-catarsis

Enlaces fantasma del LLM (no existe canción/álbum): desenlazar (quitar markdown
link, conservar el texto):
  /extremoduro/pedra
  /robe/pedra
  /robe/la-ley-innata
  /extremoduro/somos-unos-animales/tu-en-tu-casa-nosotros-en-la-hoguera
"""
from __future__ import annotations

import re

from sqlalchemy import select

from app.db.models import SeoContent
from app.db.session import SessionLocal

REPLACEMENTS = {
    "/extremoduro/agila/abre-el-pecho-y-registra":
        "/extremoduro/agila/abreme-el-pecho-y-registra",
    "/extremoduro/iros-todos-a-tomar-por-culo/bri-bri-bli-bli-en-directo":
        "/extremoduro/iros-todos-a-tomar-por-culo/bri-bri-bli-bli-en-el-mas-sucio-rincon-de-mi-negro-corazon-en-directo",
    "/robe/mayeutica/despues-de-la-catarsis":
        "/robe/mayeutica/primer-movimiento-despues-de-la-catarsis",
}

UNLINK_URLS = {
    "/extremoduro/pedra",
    "/robe/pedra",
    "/robe/la-ley-innata",
    "/extremoduro/somos-unos-animales/tu-en-tu-casa-nosotros-en-la-hoguera",
    "/extremoduro/tu-en-tu-casa-nosotros-en-la-hoguera",
}


def main() -> None:
    with SessionLocal() as db:
        contents = db.execute(
            select(SeoContent).where(SeoContent.published.is_(True))
        ).scalars().all()

        replaced = 0
        unlinked = 0
        affected_rows = 0

        for sc in contents:
            body = sc.body_md or ""
            new_body = body

            for old, new in REPLACEMENTS.items():
                count = new_body.count(f"]({old})")
                if count:
                    new_body = new_body.replace(f"]({old})", f"]({new})")
                    replaced += count

            # Desenlazar: [texto](url-fantasma) → texto
            for fantasma in UNLINK_URLS:
                pattern = re.compile(
                    r"\[([^\]]+)\]\(" + re.escape(fantasma) + r"\)"
                )
                new_body, n = pattern.subn(r"\1", new_body)
                unlinked += n

            if new_body != body:
                sc.body_md = new_body
                affected_rows += 1

        db.commit()

        print(f"Reemplazos aplicados: {replaced}")
        print(f"Enlaces fantasma desenlazados: {unlinked}")
        print(f"SeoContent actualizados: {affected_rows}")


if __name__ == "__main__":
    main()
