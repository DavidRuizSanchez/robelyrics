// Fusión de las relaciones verificadas (`entity_relations`, campo `jsonld_verificadas`
// de la API) en el nodo principal de una ficha. Plan de datos estructurados, fase 1.
//
// Dos reglas, para no romper lo que ya se sirve:
// - No duplica: una relación cuyo destino (por @id, o por nombre si no tiene) ya está
//   en esa propiedad no se añade.
// - Lo que ya sale suelto se queda suelto: si el destino ya está, NO se sustituye por
//   la versión con rol y fechas. Envolverlo en un Role cambiaría «persona · memberOf →
//   grupo» por «persona · memberOf» + «rol · memberOf → grupo», y la auditoría de
//   contención (`jsonld_audit`) lo contaría como pérdida.
//
// Con `relaciones` vacío o null no toca nada: la ficha sale idéntica.

type Nodo = Record<string, unknown>;

function destinoDe(prop: string, v: unknown): string | null {
  if (typeof v === "string") return `lit:${v}`;
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const nodo = v as Nodo;
  // En un Role, el destino es lo que envuelve (la misma propiedad, repetida dentro).
  const dentro = nodo[prop];
  const objetivo =
    dentro && typeof dentro === "object" && !Array.isArray(dentro) ? (dentro as Nodo) : nodo;
  if (typeof objetivo["@id"] === "string") return `id:${objetivo["@id"]}`;
  if (typeof objetivo.name === "string") return `name:${objetivo.name.toLowerCase()}`;
  return null;
}

export function fusionarVerificadas(
  schema: Nodo,
  relaciones: Record<string, unknown> | null | undefined,
): void {
  const lista = (v: unknown) => (Array.isArray(v) ? v : [v]);
  for (const [prop, valor] of Object.entries(relaciones || {})) {
    const previo = schema[prop];
    const vistos = new Set(
      previo === undefined
        ? []
        : lista(previo)
            .map((x) => destinoDe(prop, x))
            .filter((d): d is string => d !== null),
    );
    const nuevos = lista(valor).filter((x) => {
      const d = destinoDe(prop, x);
      if (d && vistos.has(d)) return false;
      if (d) vistos.add(d);
      return true;
    });
    if (nuevos.length === 0) continue;
    schema[prop] = previo === undefined ? nuevos : [...lista(previo), ...nuevos];
  }
}

// Copia del nodo con las verificadas fusionadas: para las páginas que montan el
// nodo dentro del propio `buildGraph([...])`.
export function conVerificadas(
  nodo: Nodo,
  relaciones: Record<string, unknown> | null | undefined,
): Nodo {
  const copia = { ...nodo };
  fusionarVerificadas(copia, relaciones);
  return copia;
}

// Etiqueta en español de cada propiedad que puede salir de `entity_relations`
// (también las inversas que se derivan al servir). Un test de la API recorre los
// predicados de `data/relaciones.yaml` y sus inversas contra este mapa.
export const ETIQUETAS_RELACION: Record<string, string> = {
  memberOf: "Miembro de",
  member: "Miembros",
  founder: "Fundado por",
  birthPlace: "Nació en",
  deathPlace: "Murió en",
  foundingLocation: "Fundado en",
  producer: "Producción",
  contributor: "Créditos",
  containedInPlace: "Situado en",
  homeLocation: "Vive en",
  worksFor: "Trabaja en",
  affiliation: "Vinculado a",
  alumniOf: "Estudió en",
  colleague: "Colegas",
  location: "Sede",
  parentOrganization: "Pertenece a",
  subOrganization: "Incluye",
  isPartOf: "Forma parte de",
  hasPart: "Incluye",
  about: "Trata de",
  subjectOf: "Aparece en",
  recordedAt: "Grabado en",
};

export type RelacionVisible = {
  etiqueta: string;
  nombre: string;
  href: string | null;
  detalle: string | null;
};

// Lo que se pinta sale del MISMO fragmento que se marca: así no pueden divergir
// («lo que se marca, se ve», plan de datos estructurados). Los `sameAs` son
// identidad, no relación: no se pintan. `excluir`: rutas que la ficha ya enseña
// (no se repiten). `sinEnlace`: rutas que ya enlaza el CUERPO; esas se nombran sin
// enlace, porque el cuerpo manda: sus enlaces no se tocan (David, 13-11-2026) y
// así se mantiene «1 por destino».
export function relacionesVisibles(
  relaciones: Record<string, unknown> | null | undefined,
  excluir: Iterable<string> = [],
  sinEnlace: Iterable<string> = [],
): RelacionVisible[] {
  const fuera = new Set(excluir);
  const delCuerpo = new Set(sinEnlace);
  // «1 por destino» también DENTRO de la sección: Uoho produce Agila y toca en él, y
  // salía enlazado dos veces (13-11-2026). La segunda vez se nombra sin enlace.
  const yaEnlazados = new Set<string>();
  const out: RelacionVisible[] = [];
  for (const [prop, valor] of Object.entries(relaciones || {})) {
    if (prop === "sameAs" || prop.startsWith("@")) continue;
    const etiqueta = ETIQUETAS_RELACION[prop] ?? prop;
    for (const v of Array.isArray(valor) ? valor : [valor]) {
      if (!v || typeof v !== "object") continue;
      const nodo = v as Nodo;
      const dentro = nodo[prop];
      const destino =
        dentro && typeof dentro === "object" && !Array.isArray(dentro) ? (dentro as Nodo) : nodo;
      const nombre = typeof destino.name === "string" ? destino.name : null;
      if (!nombre) continue;
      const url = typeof destino.url === "string" ? destino.url : null;
      const href = url && typeof destino["@id"] === "string" ? url.replace(/^https?:\/\/[^/]+/, "") : null;
      if (href && fuera.has(href)) continue;
      const partes = [
        typeof nodo.roleName === "string" ? nodo.roleName : null,
        typeof nodo.startDate === "string"
          ? `desde ${nodo.startDate}${typeof nodo.endDate === "string" ? ` hasta ${nodo.endDate}` : ""}`
          : typeof nodo.endDate === "string"
            ? `hasta ${nodo.endDate}`
            : null,
      ].filter((x): x is string => !!x);
      const enlazar = href && !delCuerpo.has(href) && !yaEnlazados.has(href) ? href : null;
      if (enlazar) yaEnlazados.add(enlazar);
      out.push({ etiqueta, nombre, href: enlazar, detalle: partes.length ? partes.join(", ") : null });
    }
  }
  return out;
}
