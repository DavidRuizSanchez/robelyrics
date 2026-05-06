/**
 * Resolutor tolerante de slugs.
 *
 * Cuando el usuario teclea una URL con un slug abreviado / con-sin-guiones /
 * más-largo-de-la-cuenta, intentamos encontrar el slug canónico para hacer
 * 308 al correcto. Reglas de prioridad:
 *
 *   1. Exact (lo gestiona el endpoint, no llega aquí).
 *   2. Prefix único: pedido = "lucha-contigo" → real = "lucha-contigo-hoy-..."
 *   3. Inverse-prefix: el pedido contiene el real entero como prefix.
 *      pedido = "destrozares-canciones-para-el-final-de-los-tiempos"
 *      → real = "destrozares" (el slug del álbum es más corto que lo escrito).
 *   4. Normalizado: ignora guiones internos.
 *      pedido = "jd-la-central-nuclear" → real = "j-d-la-central-nuclear"
 *      pedido = "calle-esperanza-sn"     → real = "calle-esperanza-s-n"
 *
 * Si una estrategia da match único, devolvemos ese slug. Si hay 0 ó ≥2
 * candidatos en una estrategia, pasamos a la siguiente. Si nada pega → null.
 */
export function resolveSlug(pedido: string, slugs: string[]): string | null {
  const norm = (s: string) => s.replace(/-/g, "").toLowerCase();

  // 2. Prefix único
  const conPrefijo = slugs.filter((s) => s.startsWith(`${pedido}-`));
  if (conPrefijo.length === 1) return conPrefijo[0];

  // 3. Inverse-prefix: el pedido empieza por algún slug real + "-"
  const inversos = slugs.filter((s) => pedido.startsWith(`${s}-`));
  if (inversos.length === 1) return inversos[0];

  // 4. Normalizado (sin guiones)
  const pedidoNorm = norm(pedido);
  const normalizados = slugs.filter((s) => norm(s) === pedidoNorm);
  if (normalizados.length === 1) return normalizados[0];

  return null;
}
