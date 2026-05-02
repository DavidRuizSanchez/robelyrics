// Resalta las palabras de `query` que aparezcan en `text`, ignorando
// acentos, mayúsculas y palabras vacías cortas (artículos, conjunciones).
// Devuelve un array de fragmentos React listo para renderizar.

import React from "react";

const STOPWORDS = new Set([
  "a", "al", "el", "la", "lo", "los", "las", "un", "una", "unos", "unas",
  "y", "o", "u", "ni", "que", "qué", "cual", "cuál",
  "de", "del", "en", "con", "sin", "por", "para", "sobre",
  "se", "te", "me", "le", "les", "nos", "os",
  "es", "ser", "fue", "era", "soy", "está", "estar",
  "yo", "tu", "tú", "él", "ella", "nosotros",
  "si", "no", "ya", "muy", "más",
]);

function normalize(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

export function HighlightQuery({
  text,
  query,
  className = "",
}: {
  text: string;
  query: string;
  className?: string;
}) {
  // Tokenizar query → palabras significativas
  const tokens = query
    .split(/\s+/)
    .map((t) => t.replace(/[^\p{L}\p{N}]/gu, ""))
    .filter((t) => t.length >= 3 && !STOPWORDS.has(normalize(t)));

  if (tokens.length === 0) {
    return <span className={className}>{text}</span>;
  }

  // Construir un único regex global con grupos de captura
  const escapedTokens = tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escapedTokens.join("|")})`, "giu");

  // Para acent-insensitive, hacemos el split sobre la versión normalizada.
  // Pero queremos preservar el texto ORIGINAL en el render. Trick:
  // recorrer carácter a carácter trackeando posición.
  const normalizedText = normalize(text);
  const matches: { start: number; end: number }[] = [];
  for (const tok of tokens) {
    const normTok = normalize(tok);
    if (!normTok) continue;
    let idx = 0;
    while ((idx = normalizedText.indexOf(normTok, idx)) !== -1) {
      // Boundary check (anterior y posterior): no marcar dentro de otra palabra
      const before = idx === 0 ? " " : normalizedText[idx - 1];
      const afterIdx = idx + normTok.length;
      const after = afterIdx >= normalizedText.length ? " " : normalizedText[afterIdx];
      if (!/[\p{L}\p{N}]/u.test(before) && !/[\p{L}\p{N}]/u.test(after)) {
        matches.push({ start: idx, end: afterIdx });
      }
      idx = afterIdx;
    }
  }

  if (matches.length === 0) {
    return <span className={className}>{text}</span>;
  }

  // Ordenar y fusionar matches solapados
  matches.sort((a, b) => a.start - b.start);
  const merged: { start: number; end: number }[] = [];
  for (const m of matches) {
    const last = merged[merged.length - 1];
    if (last && m.start <= last.end) {
      last.end = Math.max(last.end, m.end);
    } else {
      merged.push({ ...m });
    }
  }

  // Render
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const m of merged) {
    if (m.start > cursor) {
      parts.push(text.slice(cursor, m.start));
    }
    parts.push(
      <mark
        key={m.start}
        className="bg-amber-500/20 text-amber-100 rounded px-0.5"
      >
        {text.slice(m.start, m.end)}
      </mark>
    );
    cursor = m.end;
  }
  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }

  return <span className={className}>{parts}</span>;
}
