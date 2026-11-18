"""Relaciones de serie: lo que cada semana entra solo en la cola del panel.

Plan de relaciones (18-11-2026), PR E. Una entidad, un disco o un lugar que se dé de alta
entra aquí sin que nadie tenga que acordarse:

1. `identidades` → `sameAs` nuevas (Q-ID, MBID), como PENDIENTES.
2. `descubrir` → relaciones nuevas de Wikidata y MusicBrainz, como PENDIENTES.
3. Se cargan con `seed_relaciones` (que lo valida todo; si algo falla, no carga nada).
4. `propuestas` → las entidades sin página que salen de ahí.

Nada se publica solo: lo pendiente no se sirve hasta que alguien lo aprueba en
`/biblioteca/admin/entidades`. Lo ya cargado (cualquier estado) no se vuelve a proponer.
Los conciertos no van aquí: su lista de candidatos (el CSV propio) vive fuera del
contenedor y se pasa a mano con `scripts.relaciones.conciertos`.

    python -m scripts.relaciones.semanal [--seco]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def _correr(*args: str) -> int:
    print("→", " ".join(args), flush=True)
    return subprocess.call([sys.executable, "-m", *args])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seco", action="store_true", help="genera y valida, no carga")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="relaciones_") as tmp:
        dir_id, dir_rel = Path(tmp, "id"), Path(tmp, "rel")
        if _correr("scripts.relaciones.identidades", "--salida", str(dir_id)):
            sys.exit(1)
        carga = ["scripts.seed_relaciones", "--yaml", str(dir_id / "identidades.yaml")]
        if _correr(*carga, *(["--dry-run"] if args.seco else [])):
            sys.exit(1)
        if _correr("scripts.relaciones.descubrir", "--salida", str(dir_rel)):
            sys.exit(1)
        carga = ["scripts.seed_relaciones", "--yaml", str(dir_rel / "relaciones_candidatas.yaml")]
        if _correr(*carga, *(["--dry-run"] if args.seco else [])):
            sys.exit(1)
        if not args.seco:
            _correr("scripts.relaciones.propuestas", "--descubrir",
                    str(dir_rel / "propuestas_entidades.csv"))


if __name__ == "__main__":
    main()
