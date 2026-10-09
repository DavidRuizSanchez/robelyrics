"""Revista de los posts atascados en `pending_review`: dice cuáles son
publicables, cuáles duplican algo que ya está en la web y cuáles no deberían
salir nunca.

Los posts caen en `pending_review` cuando el fact-check, una cita de letra en
zona gris o el gate de foco dudan de algo. Ahí se quedan hasta que un humano
decide. Cuando la cola lleva meses, decidir a ojo es inviable: este script vuelve
a pasarles los controles y ordena la cola por lo que hay que hacer con cada uno.

NO publica ni descarta nada. Solo mira y ordena; la decisión sigue siendo tuya.

Veredictos, de peor a mejor:
  DUPLICADO   otro post ya publicado cubre lo mismo (canibalización en Google)
  CITA        una cita de letra no verificable lo bloquea (regla dura, no evadible)
  HECHOS      contradice el catálogo, o la web dejó algo por confirmar
  FLOJO       el editor jefe lo rechaza: genérico o sin sustancia
  PUBLICABLE  pasa todos los controles de hoy

Uso:
    python -m scripts.blog.triage_pending
    python -m scripts.blog.triage_pending --sin-llm   # solo lo determinista y gratis
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime

from app.db.models import Post
from app.db.session import SessionLocal

# La detección de duplicados la comparte con el aviso diario: si se copiara
# aquí, los dos dirían cosas distintas en cuanto alguien moviera el umbral.
from app.services.triage import duplicado_de


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sin-llm", action="store_true",
                        help="salta el gate de rigor (no gasta llamadas)")
    args = parser.parse_args()

    from app.services.fact_check import check_body
    from app.services.lyric_guard import check_lyrics

    hoy = datetime.now(UTC)
    with SessionLocal() as db:
        pendientes = (
            db.query(Post)
            .filter(Post.status == "pending_review")
            .order_by(Post.created_at)
            .all()
        )
        publicados = db.query(Post).filter(Post.status == "published").all()
        print(f"Pendientes: {len(pendientes)} · publicados: {len(publicados)}\n")

        # Un pendiente puede duplicar a otro pendiente: el más antiguo manda.
        vistos: list[Post] = list(publicados)
        filas = []
        for p in pendientes:
            edad = (hoy - p.created_at).days
            palabras = len((p.body_md or "").split())
            motivos: list[str] = []

            dup = duplicado_de(p, vistos)
            citas = check_lyrics(db, p.body_md or "")
            hechos = check_body(db, p.body_md or "", use_web=False)

            if dup:
                otro, ratio = dup
                estado = "DUPLICADO"
                donde = "publicado" if otro.status == "published" else "pendiente"
                motivos.append(f"{int(ratio * 100)}% de «{otro.title[:44]}» ({donde} #{otro.id})")
            elif citas.blocking:
                estado = "CITA"
                motivos.append(citas.blocking[0].reason)
            elif citas.to_review:
                estado = "CITA"
                motivos.append(f"zona gris: {citas.to_review[0].reason}")
            elif hechos.autofixes or hechos.to_review:
                estado = "HECHOS"
                v = (hechos.autofixes + hechos.to_review)[0]
                motivos.append(f"{v.claim.type}: {v.claim.subject}")
            else:
                estado = "PUBLICABLE"

            # El rigor solo se pregunta a lo que sigue vivo: es lo único que cuesta.
            if estado == "PUBLICABLE" and not args.sin_llm:
                from app.services.editorial_review import review as editorial_review
                subject = (p.target_keyword or p.title or "").strip()
                v = editorial_review(p.body_md or "", kind=p.kind, subject=subject)
                if v.verdict == "reject":
                    estado = "FLOJO"
                    motivos.append(f"score {v.score}: {'; '.join(v.reasons)[:70]}")
                else:
                    motivos.append(f"rigor {v.score}")

            vistos.append(p)
            filas.append((estado, p, edad, palabras, "; ".join(motivos)))

        orden = {"DUPLICADO": 0, "CITA": 1, "HECHOS": 2, "FLOJO": 3, "PUBLICABLE": 4}
        filas.sort(key=lambda f: (orden[f[0]], -f[2]))
        for estado, p, edad, palabras, motivo in filas:
            print(f"{estado:11} #{p.id:<4} {edad:>4}d {palabras:>5}p  {p.title[:52]}")
            if motivo:
                print(f"{'':11} └─ {motivo}")

        print()
        for est in orden:
            n = sum(1 for f in filas if f[0] == est)
            if n:
                print(f"  {est:11} {n}")


if __name__ == "__main__":
    main()
