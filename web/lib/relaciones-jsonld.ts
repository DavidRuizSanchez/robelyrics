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
