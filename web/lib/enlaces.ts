// Lo que se promociona en `/enlaces`, la página del enlace de la bio de Instagram.
// Se elige a mano: cambiarlo es editar esta lista y desplegar el web. El orden
// de la lista es el orden de la página. El título, el resumen y la imagen salen
// del propio contenido (registro de estudios o API del blog), nunca se copian
// aquí, para que no se queden viejos si el contenido cambia.

export type Destacado =
  | { tipo: "estudio"; slug: string }
  | { tipo: "post"; slug: string };

export const DESTACADOS: Destacado[] = [
  { tipo: "estudio", slug: "repertorio-en-directo-extremoduro-robe" },
  { tipo: "post", slug: "flores-amarillas-2027-tributo-a-robe-en-plasencia" },
];
