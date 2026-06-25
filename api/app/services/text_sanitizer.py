"""Saneado determinista de texto generado por LLM.

Red de seguridad: aunque el SYSTEM_PROMPT prohíbe el em-dash y otras marcas
de IA, el modelo a veces se cuela. `strip_ai_tells` limpia el texto de
forma mecánica antes de persistirlo.

El em-dash «—» (U+2014) y el en-dash «–» (U+2013) son el delator nº1 de
texto de ChatGPT. Los sustituimos según el contexto:
  - rodeado de espacios  " — "  → ", "   (inciso)
  - pegado entre palabras "x—y"  → "x, y"
  - al principio de línea (lista) "— item" → "- item"
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Reglas de sustitución de dashes
# --------------------------------------------------------------------------- #
_DASHES = "—–―"  # — – ―

# guion al inicio de línea (item de lista) → guion ASCII
_RE_LIST_DASH = re.compile(rf"^(\s*)[{_DASHES}]\s+", re.MULTILINE)
# " — " inciso entre espacios → ", "
_RE_SPACED_DASH = re.compile(rf"\s+[{_DASHES}]\s+")
# "palabra—palabra" pegado → "palabra, palabra"
_RE_TIGHT_DASH = re.compile(rf"(\w)[{_DASHES}](\w)")
# cualquier dash residual → coma
_RE_ANY_DASH = re.compile(rf"[{_DASHES}]")

_RE_MULTISPACE = re.compile(r"[ \t]{2,}")
_RE_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")

# Política de nombre (CRÍTICA): a Robe NO le gustaba que le llamaran "Robe
# Iniesta". Esa forma NUNCA debe aparecer en contenido público: se usa "Robe"
# (o "Roberto Iniesta" en datos formales). El \b evita tocar "Roberto Iniesta".
_RE_ROBE_INIESTA = re.compile(r"\bRobe\s+Iniesta\b", re.IGNORECASE)


def enforce_name_policy(text: str | None) -> str | None:
    """Sustituye la forma vetada 'Robe Iniesta' por 'Robe'. No toca 'Roberto
    Iniesta' (permitida)."""
    if not text:
        return text
    return _RE_ROBE_INIESTA.sub("Robe", text)


# Enlace markdown a un vídeo de YouTube: [texto](url). El front (MarkdownArticle)
# solo EMBEBE una URL de YouTube cuando va sola en su línea; un enlace markdown
# no se embebe. Convertimos esos enlaces en URL desnuda para que se reproduzcan.
_RE_YT_MD_LINK = re.compile(
    r"\[[^\]]*\]\((https?://(?:www\.)?(?:youtube\.com/watch\?[^)\s]*v=[\w-]+[^)\s]*"
    r"|youtu\.be/[\w-]+[^)\s]*|youtube\.com/(?:embed|shorts)/[\w-]+[^)\s]*))\)"
)


def embed_youtube_links(text: str | None) -> str | None:
    """Convierte enlaces markdown de YouTube `[txt](url)` en la URL desnuda en su
    PROPIA línea, para que el front la embeba como reproductor. Idempotente y sin
    duplicar: si esa URL ya aparece desnuda en el texto, elimina el enlace."""
    if not text:
        return text
    out = text

    def _repl(m: re.Match) -> str:
        url = m.group(1)
        # Si ya está la URL desnuda en el cuerpo, no la repitas.
        if re.search(rf"^\s*{re.escape(url)}\s*$", out, flags=re.MULTILINE):
            return ""
        return f"\n\n{url}\n\n"

    out = _RE_YT_MD_LINK.sub(_repl, out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def strip_ai_tells(text: str | None) -> str | None:
    """Limpia marcas de IA de `text`. Devuelve None si la entrada es None.

    No toca enlaces markdown ni el contenido entre comillas (aunque las
    sustituciones son seguras igualmente — un em-dash dentro de una cita
    también es indeseable)."""
    if text is None:
        return None
    if not text:
        return text

    out = text
    # 1) guion de lista al inicio de línea
    out = _RE_LIST_DASH.sub(r"\1- ", out)
    # 2) inciso con espacios → coma
    out = _RE_SPACED_DASH.sub(", ", out)
    # 3) dash pegado entre palabras → coma
    out = _RE_TIGHT_DASH.sub(r"\1, \2", out)
    # 4) cualquier dash suelto restante → coma
    out = _RE_ANY_DASH.sub(", ", out)
    # 5) normalizar espacios
    out = _RE_MULTISPACE.sub(" ", out)
    out = _RE_SPACE_BEFORE_PUNCT.sub(r"\1", out)
    # 6) limpiar comas duplicadas que hayan podido surgir
    out = re.sub(r",\s*,", ",", out)
    # 7) política de nombre: nunca "Robe Iniesta"
    out = _RE_ROBE_INIESTA.sub("Robe", out)
    return out


# --------------------------------------------------------------------------- #
# Normalización de jerarquía de headings
# --------------------------------------------------------------------------- #
_RE_ATX = re.compile(r"^(#{1,6})(\s+\S)")


def normalize_headings(body_md: str | None) -> str | None:
    """Ajusta los niveles de heading del cuerpo para que el más alto sea H2.

    El título de la página se renderiza como H1, así que el cuerpo NO debe
    empezar en H1 ni saltarse el H2 (p.ej. body todo en `###` → H1, H3...).
    Esta función desplaza todos los headings de forma uniforme para que el
    nivel más alto presente pase a ser H2, preservando el anidamiento
    relativo. Respeta los bloques de código fenced (``` ... ```).
    """
    if not body_md:
        return body_md
    lines = body_md.split("\n")

    # 0) Regla global: NUNCA enlazar dentro de un heading. Quita los enlaces
    # markdown de las líneas de encabezado (conserva el texto). Siempre, aunque
    # luego no haya que desplazar niveles.
    _link_re = re.compile(r"\[([^\]]+)\]\([^)]+\)")
    in_code = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and _RE_ATX.match(ln):
            lines[i] = _link_re.sub(r"\1", ln)
    body_md = "\n".join(lines)

    # 1) Detectar el nivel mínimo de heading fuera de bloques de código.
    in_code = False
    levels: list[int] = []
    for ln in lines:
        if ln.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _RE_ATX.match(ln)
        if m:
            levels.append(len(m.group(1)))
    if not levels:
        return body_md

    shift = 2 - min(levels)  # queremos que el más alto sea H2
    if shift == 0:
        return body_md

    # 2) Aplicar el desplazamiento (clamp 1..6).
    in_code = False
    out: list[str] = []
    for ln in lines:
        if ln.lstrip().startswith("```"):
            in_code = not in_code
            out.append(ln)
            continue
        if not in_code:
            m = _RE_ATX.match(ln)
            if m:
                new_level = max(1, min(6, len(m.group(1)) + shift))
                ln = "#" * new_level + ln[len(m.group(1)):]
        out.append(ln)
    return "\n".join(out)
