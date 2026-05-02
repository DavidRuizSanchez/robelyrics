/**
 * Datos de display para la home y la discografía.
 * Estos datos NO sustituyen al catálogo real (que viene del API);
 * son sólo paleta de colores por disco y versos rotativos del hero.
 */

export const ROTATING_LINES = [
  { text: "Déjame en paz, la luna me ilumina", song: "Sol", album: "Iros todos a tomar por culo", year: 1996 },
  { text: "Buscando una luna que alumbre los cielos", song: "Buscando una luna", album: "Iros todos a tomar por culo", year: 1996 },
  { text: "Y soñé que era un pez naranja", song: "So payaso", album: "Iros todos a tomar por culo", year: 1996 },
  { text: "Abre la puerta, que soy el diablo", song: "El día de la bestia", album: "Agila", year: 1996 },
  { text: "Se acabó la primavera", song: "Papel secante", album: "Canciones prohibidas", year: 1998 },
  { text: "Me estoy quitando", song: "Me estoy quitando", album: "Iros todos a tomar por culo", year: 1996 },
  { text: "No hay suelo debajo de mis botas", song: "Ininteligible", album: "Se nos lleva el aire", year: 2024 },
] as const;

/**
 * Mapping `album.slug` → color hex para representar el disco visualmente
 * (cuadrados degradados en la lista de discografía).
 * Cualquier disco no listado usará el color por defecto.
 */
export const DISCOGRAPHY_COLORS: Record<string, string> = {
  "rock-transgresivo": "#8b3a3a",
  "somos-unos-animales": "#7a4a2e",
  deltoya: "#9c5a2a",
  "donde-estan-mis-amigos": "#a2602f",
  agila: "#a06a30",
  "iros-todos-a-tomar-por-culo": "#b8722a",
  "canciones-prohibidas": "#7a3a3a",
  "yo-minoria-absoluta": "#5a3a7a",
  "la-ley-innata": "#3a5a4a",
  "material-defectuoso": "#6a4a2a",
  "para-todos-los-publicos": "#4a3a5a",
  "lo-que-aletea-en-nuestras-cabezas": "#5a4a3a",
  destrozares: "#3a4a5a",
  mayeutica: "#5a3a4a",
  "se-nos-lleva-el-aire": "#7a3a5a",
};

export const DEFAULT_DISC_COLOR = "#5a3a3a";
