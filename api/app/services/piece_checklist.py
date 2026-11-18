"""Un mismo listón para quien escribe, quien recorta y quien juzga una pieza del blog.

Plan del blog (18-11-2026). El post del 10.º aniversario de «Destrozares» se escribió
con un encargo que pedía «el sello», el filtro de foco le quitó la sección «El lugar
del álbum en la obra de Robe» (que el encargo y la rúbrica exigían) y el juez lo
descartó por no dar «fecha de publicación ni contexto de grabación, ni el sello». Tres
piezas leyendo tres listas distintas, y una de ellas pedía un dato que nadie había
buscado.

Aquí vive la lista por tipo de pieza. Cada punto dice qué hecho duro lo cubre: si el
hecho está, se exige; si no está en ninguna fuente, se quita del encargo y se le dice
al juez que no consta, para que no castigue lo que no se puede escribir.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Punto:
    clave: str
    encargo: str            # lo que se le pide al redactor
    # Prefijos de línea de los hechos duros que lo cubren. Vacío = siempre se puede
    # escribir con el material (no depende de un dato concreto).
    cubierto_por: tuple[str, ...] = ()
    # Si ningún hecho duro lo cubre, qué se le pregunta al corpus para buscarlo
    # («{t}» = el título). Un punto sin consultas y sin hecho, no se exige.
    consultas: tuple[str, ...] = ()


LISTAS: dict[str, tuple[Punto, ...]] = {
    "album-anniversary": (
        Punto("fecha", "la fecha de publicación exacta", ("Fecha de publicación:",)),
        Punto("sello", "el sello que lo editó", ("Sello:",)),
        Punto("produccion", "quién participó en la producción", ("Producción:",)),
        Punto("grabacion", "la grabación: cuándo, dónde y con quién",
              ("Grabación:",),
              ("cómo se grabó el disco {t}", "estudio y producción de {t}")),
        Punto("canciones", "las canciones clave, nombradas por su TÍTULO y con un verso "
              "literal de su letra al comentarlas", ("Tracklist",)),
        Punto("sonido", "el sonido y la formación que lo toca", (),
              ("sonido y arreglos del disco {t}", "músicos que tocan en {t}")),
        Punto("recepcion", "cómo se recibió (primer sencillo, ventas, listas) si consta",
              ("Listas:", "Certificación:", "Primer sencillo:")),
        # La muerte de Robe NO se exige aquí (David, 18-11-2026: solo donde merece ir).
        Punto("trayectoria", "su lugar en la trayectoria (los discos de antes y de "
              "después)", ("Discografía:",)),
    ),
}


# «Cómo se hizo un disco» (idea de catálogo) pide lo mismo que su aniversario.
LISTAS["album-historia"] = LISTAS["album-anniversary"]


@dataclass
class Listón:
    tipo: str
    exigibles: list[Punto]
    no_constan: list[Punto]

    def encargo(self) -> str:
        """El encargo del redactor: SOLO lo que se puede escribir con lo que hay."""
        if not self.exigibles:
            return ""
        return ("Cuenta, por este orden de importancia: "
                + "; ".join(p.encargo for p in self.exigibles) + ".")

    def enfoque(self) -> str:
        """Para el filtro de foco: lo que el encargo pide NO es desviación."""
        if not self.exigibles:
            return ""
        return ("Por encargo, la pieza DEBE tratar: "
                + "; ".join(p.encargo for p in self.exigibles)
                + ". Esas secciones no son desviación y no se recortan.")

    def para_el_juez(self) -> str:
        """Lo que el juez no debe exigir porque no consta en ninguna fuente."""
        if not self.no_constan:
            return ""
        return ("Estos datos NO constan en ninguna fuente verificada (se buscaron): "
                + "; ".join(p.encargo for p in self.no_constan)
                + ". Su ausencia no es motivo de rechazo; inventarlos sí lo sería.")


def _cubierto(p: Punto, lineas: list[str]) -> bool:
    return any(ln.startswith(pre) for ln in lineas for pre in p.cubierto_por)


def pendientes(tipo: str, hechos_duros: str) -> list[Punto]:
    """Puntos que los hechos duros no cubren y que se pueden BUSCAR en el corpus."""
    lineas = [ln.strip() for ln in (hechos_duros or "").splitlines()]
    return [p for p in LISTAS.get(tipo, ()) if p.consultas and not _cubierto(p, lineas)]


def liston(tipo: str, hechos_duros: str, con_material: set[str] | None = None) -> Listón | None:
    """El listón de `tipo`: se exige lo que cubren los hechos duros y lo que la búsqueda
    en el corpus encontró (`con_material`, claves de punto); lo demás «no consta»."""
    puntos = LISTAS.get(tipo)
    if not puntos:
        return None
    lineas = [ln.strip() for ln in (hechos_duros or "").splitlines()]
    exigibles, faltan = [], []
    for p in puntos:
        libre = not p.cubierto_por and not p.consultas   # se escribe con el material
        if libre or _cubierto(p, lineas) or (con_material is not None and p.clave in con_material):
            exigibles.append(p)
        elif p.consultas and con_material is None:
            # Sin saber qué encontró la búsqueda (el juez no lo sabe), un punto buscable es
            # DESCONOCIDO: ni se exige ni se declara inexistente. Decirle al juez que «el
            # sonido y la formación no constan» con la formación en el texto le hacía
            # leerla como inventada: 0 sobre 100 (18-11-2026).
            continue
        else:
            faltan.append(p)
    return Listón(tipo, exigibles, faltan)
