// Enlazado interno: 1 enlace por destino y página (regla de David, 11-11-2026).
//
// El cuerpo no repite un destino que ya enlaza la plantilla, ni uno que ya
// enlazó él mismo más arriba: ese enlace se pinta como texto. Se hace AL
// SERVIR porque la plantilla es dinámica (tracklist, pertenencias, temas…) y
// el cuerpo vive en la BD. Medido el 11-11-2026 sobre el sitemap: 494 parejas
// cuerpo↔plantilla y 15 cuerpo↔cuerpo. Misma normalización que
// `api/app/services/link_policy.norm_path`.

const SITE = /^(?:https?:)?\/\/(?:www\.)?entreinteriores\.com(?=[/?#]|$)/i;

/** Ruta interna comparable (`/a/b`), o null si el enlace es externo. */
export function normPath(href?: string | null): string | null {
  let u = (href ?? "").trim();
  if (!u || /^(mailto:|tel:|javascript:|#)/i.test(u)) return null;
  if (SITE.test(u)) u = u.replace(SITE, "");
  else if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(u) || !u.startsWith("/")) return null;
  u = u.split(/[?#]/, 1)[0];
  return "/" + u.replace(/^\/+|\/+$/g, "");
}

/** Conjunto de rutas normalizadas (ignora externas y vacías). */
export function rutas(hrefs: Iterable<string | null | undefined>): Set<string> {
  const out = new Set<string>();
  for (const h of hrefs) {
    const p = normPath(h);
    if (p) out.add(p);
  }
  return out;
}

// Enlace markdown inline (no imágenes), con UN nivel de corchetes en el texto: el
// mismo patrón que `link_policy.ENLACE` en el backend.
const ENLACE_MD = /(?<!!)\[(?:[^[\]]|\[[^[\]]*\])+\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;

/** Rutas internas que enlaza un cuerpo en markdown. */
export function rutasDelCuerpo(md?: string | null): Set<string> {
  return rutas([...(md ?? "").matchAll(ENLACE_MD)].map((m) => m[1]));
}
