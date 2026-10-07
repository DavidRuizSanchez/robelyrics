// Qué dato del estudio del repertorio le toca a cada página, y adónde enlaza.
//
// El enlace al estudio va UNA vez por página y solo donde el estudio habla de esa
// página en concreto: las once sin registro, las canciones que comenta, los
// discos que tienen alguna de las once, los lugares y los dos artistas. En el resto
// de fichas de canción la cifra va con su atribución a setlist.fm y sin enlace:
// ciento y pico enlaces idénticos al mismo destino no suman nada.

import { ATRAS, DUMB, TOP } from "./datos-repertorio";
import { DATOS } from "./datos-por-pagina";

export const ESTUDIO_PATH = "/estudios/repertorio-en-directo-extremoduro-robe";

export const SETLISTFM: Record<string, string> = {
  extremoduro: "https://www.setlist.fm/stats/extremoduro-13d68da1.html",
  robe: "https://www.setlist.fm/stats/robe-63c74607.html",
};

/** Anclas de las secciones de `RepertorioEnDirecto`. */
export const ANCLA = {
  once: "once",
  mapa: "mapa",
  masTocadas: "mas-tocadas",
  extremoduroVsRobe: "extremoduro-vs-robe",
  seQuedoAtras: "lo-que-se-quedo-atras",
  legado: "legado",
} as const;

const norm = (t: string) =>
  t
    .replace(/\s*[([].*$/, "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");

// La sección que habla de cada canción, por orden de preferencia: el contraste
// Extremoduro/Robe es más específico que el ranking general.
const SECCION_POR_TITULO = new Map<string, string>();
for (const [t] of TOP) SECCION_POR_TITULO.set(norm(t), ANCLA.masTocadas);
for (const [t] of ATRAS) SECCION_POR_TITULO.set(norm(t), ANCLA.seQuedoAtras);
for (const [t] of DUMB) SECCION_POR_TITULO.set(norm(t), ANCLA.extremoduroVsRobe);

export const es = (n: number) => n.toLocaleString("es-ES");
export const coma = (n: number) => String(n).replace(".", ",");

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
export function fechaLarga(iso: string | null): string | null {
  const m = iso && /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  return `${Number(m[3])} de ${MESES[Number(m[2]) - 1]} de ${m[1]}`;
}

export function datoCancion(path: string, titulo: string) {
  const d = DATOS.canciones[path];
  if (!d) return null;
  const ancla = d.once ? ANCLA.once : SECCION_POR_TITULO.get(norm(titulo)) ?? null;
  return { ...d, ancla };
}

export const datoDisco = (path: string) => DATOS.discos[path] ?? null;
export const datoArtista = (slug: string) => DATOS.artistas[slug] ?? null;
export const datoLugar = (slug: string) => DATOS.lugares[slug] ?? null;
