// Marca y constantes del sitio — FUENTE ÚNICA.
// Antes `SITE_URL` estaba redefinido en 11+ ficheros; todo importa de aquí.
// Este módulo NO importa nada del proyecto (evita imports circulares con
// schema-graph.ts, que sí importa de aquí).

export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const SITE_NAME = "Entre Interiores";
export const SITE_ALT_NAME = "Cancionero de Robe y Extremoduro";
export const SITE_DESCRIPTION =
  "Disco a disco, canción a canción: el universo de Robe y Extremoduro contado por sus letras y por la comunidad de fans.";
export const SITE_LANG = "es-ES";
export const SITE_INSTAGRAM = "https://www.instagram.com/entreinterioresrobe/";
// Logo cuadrado servible (existe en web/public). Para Organization.logo.
export const SITE_LOGO_URL = `${SITE_URL}/logo-bomba-light-512.png`;

// @id canónicos a nivel de sitio (nodos globales del layout).
export const WEBSITE_ID = `${SITE_URL}/#website`;
export const ORGANIZATION_ID = `${SITE_URL}/#organization`;
// Person del autor: entidad canónica EXTERNA (en su web personal).
export const AUTHOR_ID = "https://davidruizsanchez.es/#person";
