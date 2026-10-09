// Registro de los estudios de datos de Entre Interiores.
//
// Va en código y no en la BD a propósito: un estudio no es contenido que genere
// el motor, es una pieza con su dataset, su documento de fuentes y su propio
// componente. Lo que sí se comparte con el resto de la web es la plantilla
// (cabecera, breadcrumbs, @graph, footer) y el sitemap.
//
// Para añadir uno: una entrada aquí + su componente en `components/estudio/`,
// enganchado en el `switch` de `app/estudios/[slug]/page.tsx`.

export type Estudio = {
  slug: string;
  /** H1 de la pieza. El `title` del <head> se compone aparte. */
  titulo: string;
  metaTitle: string;
  metaDescription: string;
  /** Resumen para el índice y para el JSON-LD. */
  resumen: string;
  datePublished: string;
  dateModified: string;
  /** Lo que el estudio mide, para el nodo Dataset. */
  mide: string[];
  /** Post del blog que cuenta el estudio en prosa, si lo hay. */
  post?: string;
  /** Periodo que cubren los datos, ISO 8601 (`1987/2024`). */
  cobertura?: string;
  /**
   * Ficheros que se publican para descargar, con su licencia. SOLO material
   * propio: lo derivado de setlist.fm se muestra con atribución pero no se
   * redistribuye (sus condiciones prohíben retener copias y obras derivadas),
   * así que nunca entra aquí ni bajo CC BY.
   */
  descargas?: { nombre: string; ruta: string; formato: string }[];
  /** Fuentes de las que parte el dataset (`isBasedOn`). */
  basadoEn?: string[];
};

export const LICENCIA_CC_BY = "https://creativecommons.org/licenses/by/4.0/";

export const ESTUDIOS: Estudio[] = [
  {
    slug: "repertorio-en-directo-extremoduro-robe",
    titulo: "Las 11 canciones de Extremoduro que nunca has escuchado en directo",
    metaTitle:
      "Estudio del repertorio en directo de Extremoduro y Robe: 591 conciertos",
    metaDescription:
      "Cruzamos los 591 conciertos documentados de Extremoduro y Robe con las 132 composiciones del catálogo. Mira el mapa de las 50 provincias, el ranking de lo más tocado y las once canciones que no consta que sonaran nunca.",
    resumen:
      "591 conciertos documentados entre 1987 y 2024, 5.581 interpretaciones contadas y 132 composiciones del catálogo. Del cruce salen once canciones sin un solo registro en directo, un mapa con las cincuenta provincias y el reparto real del repertorio entre Extremoduro y Robe.",
    datePublished: "2026-10-07",
    dateModified: "2026-10-07",
    mide: [
      "conciertos documentados por provincia, ciudad y recinto",
      "interpretaciones por canción y por disco de origen",
      "composiciones sin registro en directo",
      "versos, repeticiones y estribillos del catálogo",
    ],
    post: "canciones-extremoduro-sin-registro-en-directo",
    cobertura: "1987/2024",
    descargas: [
      {
        nombre: "Las once canciones sin registro en directo",
        ruta: "/datos/once-canciones-sin-registro-en-directo.csv",
        formato: "text/csv",
      },
    ],
    basadoEn: ["https://www.setlist.fm/", "https://musicbrainz.org/"],
  },
];

export const estudioPorSlug = (slug: string): Estudio | undefined =>
  ESTUDIOS.find((e) => e.slug === slug);
