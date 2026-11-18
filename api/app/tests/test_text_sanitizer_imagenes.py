"""Una imagen markdown en su línea tiene que sobrevivir a la limpieza del texto.

El 17-11-2026 la ficha de «El rey de la baraja» perdió una de sus dos páginas
interiores: `strip_ai_tells` se comía el salto de línea de antes de «![» (lo
trataba como un espacio delante de una exclamación) y la imagen se pegaba al
heading, donde `normalize_headings` le quitaba el destino.
"""
from app.services.text_sanitizer import normalize_headings, strip_ai_tells

CUERPO = (
    "## Dos páginas por dentro\n"
    '![Página del cómic](https://res.cloudinary.com/x/a.jpg "Nacho Nava (Altamarea, 2026).")\n'
    "\n"
    "Una de sus páginas presenta a la primera formación.\n"
    "\n"
    '![Página 87](https://res.cloudinary.com/x/b.jpg "Página 87.")\n'
    "\n"
    "Texto final."
)


def test_la_imagen_bajo_un_heading_no_se_pega_a_el():
    limpio = normalize_headings(strip_ai_tells(CUERPO))
    assert "## Dos páginas por dentro\n![Página del cómic](https://res.cloudinary.com/x/a.jpg" in limpio


def test_la_imagen_tras_un_parrafo_conserva_su_linea():
    limpio = strip_ai_tells(CUERPO)
    assert "primera formación.\n\n![Página 87](https://res.cloudinary.com/x/b.jpg" in limpio


def test_el_espacio_antes_de_un_signo_se_sigue_quitando():
    assert strip_ai_tells("Hola , qué tal ?") == "Hola, qué tal?"
