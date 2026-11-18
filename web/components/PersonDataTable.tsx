import type { ReactNode } from "react";
import Link from "next/link";
import { normPath, rutas } from "@/lib/enlazado";

type Membership = {
  artist_slug: string;
  artist_name: string;
  role: string;
  era: string | null;
  is_founder: boolean;
  is_current: boolean;
};

type WikidataRef = {
  name: string;
  wikidata_id: string;
  wikidata_url: string;
  wikipedia_url: string | null;
  internal_url: string | null;
};

type PersonDataTableDetail = {
  full_name: string;
  stage_name: string | null;
  birth_date: string | null;
  death_date: string | null;
  birth_place: string | null;
  instruments: string[];
  occupations: WikidataRef[];
  other_bands: WikidataRef[];
  memberships: Membership[];
  // Relaciones curadas (data/person_jsonld.yaml), ya resueltas por la API: lo que
  // Wikidata no tiene (grupos sin Q-ID, colegas, obras de un artista visual…).
  jsonld_relaciones?: Record<string, unknown> | null;
};

type Nodo = Record<string, unknown>;

const SITE = /^https?:\/\/[^/]+/;

function lista(v: unknown): Nodo[] {
  if (!v) return [];
  return (Array.isArray(v) ? v : [v]).filter(
    (x): x is Nodo => typeof x === "object" && x !== null,
  );
}

function texto(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

/** Nombre del nodo, enlazado a su ficha si la tiene (la API solo pone `url` si se ve). */
// Destinos ya enlazados en la página (cabecera + esta tabla, en orden): un
// destino repetido se pinta como texto (lib/enlazado.ts, regla del 11-11-2026).
type Vistos = Set<string>;

function primeraVez(vistos: Vistos, href: string | null | undefined): boolean {
  const p = normPath(href);
  if (!p) return true;
  if (vistos.has(p)) return false;
  vistos.add(p);
  return true;
}

function enlace(n: Nodo, key: string, vistos: Vistos): ReactNode {
  const nombre = texto(n.name) || "";
  const url = texto(n.url);
  return url && primeraVez(vistos, url.replace(SITE, "")) ? (
    <Link key={key} href={url.replace(SITE, "")} data-cursor="hover"
          className="text-accent hover:underline">
      {nombre}
    </Link>
  ) : (
    <span key={key}>{nombre}</span>
  );
}

function separados(nodos: ReactNode[]): ReactNode {
  return nodos.map((n, i) => (
    <span key={`s-${i}`}>
      {i > 0 && <span className="text-ink-faint"> · </span>}
      {n}
    </span>
  ));
}

function formatDateEs(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

const CORE_SLUGS = new Set(["robe", "extremoduro"]);

function describeMembership(m: Membership): string {
  const era = m.era ? ` (${m.era})` : "";
  const founder = m.is_founder ? ", fundador" : "";
  return `${m.role} en ${m.artist_name}${era}${founder}`;
}

type Row = {
  label: string;
  /** Contenido de la celda de valor (texto o JSX). */
  value: ReactNode;
};

/** Rutas internas que puede enlazar esta tabla: el cuerpo no las repite. */
export function enlacesPersonDataTable(detail: PersonDataTableDetail): string[] {
  const rel = detail.jsonld_relaciones || {};
  const grupos = lista(rel.memberOf).map((m) =>
    m["@type"] === "OrganizationRole" ? lista(m.memberOf)[0] || {} : m,
  );
  const nodos = [lista(rel.homeLocation)[0], ...grupos, ...lista(rel.colleague)];
  return [
    ...nodos.map((n) => (n ? texto(n.url)?.replace(SITE, "") : null)),
    ...detail.memberships.map((m) => `/${m.artist_slug}`),
    ...detail.other_bands.map((b) => b.internal_url),
  ].filter((h): h is string => !!h);
}

export default function PersonDataTable({
  detail,
  yaEnlazados,
}: {
  detail: PersonDataTableDetail;
  // Lo que ya enlaza la cabecera de la ficha: aquí va como texto.
  yaEnlazados?: Iterable<string>;
}) {
  const vistos: Vistos = rutas(yaEnlazados ?? []);
  const birth = formatDateEs(detail.birth_date);
  const death = formatDateEs(detail.death_date);

  // "Con Robe/Extremoduro": resumen derivado de las pertenencias al corpus.
  const coreMemberships = detail.memberships.filter((m) =>
    CORE_SLUGS.has(m.artist_slug),
  );
  const coreSummary = coreMemberships
    .map((m) => `${m.role} de ${m.artist_name}${m.era ? ` (${m.era})` : ""}`)
    .join("; ");

  const rel = detail.jsonld_relaciones || {};
  const rows: Row[] = [];

  rows.push({ label: "Nombre real", value: detail.full_name });

  const alias = detail.stage_name && detail.stage_name !== detail.full_name
    ? detail.stage_name
    : texto(rel.alternateName);
  if (alias) {
    rows.push({ label: "Alias", value: alias });
  }

  // Solo el año cuando es lo único que consta (schema.org lo admite; la columna no).
  const anyo = texto(rel.birthDate);
  if (birth) {
    rows.push({
      label: "Nacimiento",
      value: `${birth}${detail.birth_place ? ` · ${detail.birth_place}` : ""}`,
    });
  } else if (anyo && /^\d{4}$/.test(anyo)) {
    rows.push({ label: "Nacimiento", value: anyo });
  }

  const ciudad = lista(rel.homeLocation)[0];
  if (ciudad) {
    rows.push({ label: "Ciudad", value: enlace(ciudad, "ciudad", vistos) });
  }

  if (death) {
    rows.push({ label: "Fallecimiento", value: death });
  }

  if (detail.instruments.length > 0) {
    rows.push({ label: "Instrumentos", value: detail.instruments.join(" · ") });
  }

  const oficios = [
    ...detail.occupations.map((o) => o.name),
    ...lista(rel.hasOccupation).map((o) => texto(o.name) || ""),
  ].filter((o, i, todos) => o && todos.findIndex((x) => x.toLowerCase() === o.toLowerCase()) === i);
  if (oficios.length > 0) {
    rows.push({ label: "Oficios", value: oficios.join(" · ") });
  }

  const formacion = lista(rel.alumniOf);
  if (formacion.length > 0) {
    rows.push({
      label: "Formación",
      value: separados(formacion.map((f, i) => {
        const lugar = lista(f.location)[0];
        return (
          <span key={`f-${i}`}>
            {texto(f.name)}
            {lugar ? <span className="text-ink-dim"> ({texto(lugar.name)})</span> : null}
          </span>
        );
      })),
    });
  }

  if (coreSummary) {
    rows.push({ label: "Con Robe / Extremoduro", value: coreSummary });
  }

  if (detail.memberships.length > 0) {
    rows.push({
      label: "En activo / grupos",
      value: (
        <ul className="space-y-1">
          {detail.memberships.map((m, i) => (
            <li key={`mem-${i}`}>
              {primeraVez(vistos, `/${m.artist_slug}`) ? (
                <Link
                  href={`/${m.artist_slug}`}
                  data-cursor="hover"
                  className="text-accent hover:underline"
                >
                  {m.artist_name}
                </Link>
              ) : (
                <span>{m.artist_name}</span>
              )}{" "}
              <span className="text-ink-dim">· {describeMembership(m)}</span>
            </li>
          ))}
        </ul>
      ),
    });
  }

  // Grupos curados: un OrganizationRole lleva el grupo dentro, con su papel y su año.
  const grupos = lista(rel.memberOf).map((m, i) => {
    const grupo = m["@type"] === "OrganizationRole" ? lista(m.memberOf)[0] || {} : m;
    const papel = [texto(m.roleName), texto(m.startDate)].filter(Boolean).join(", ");
    return (
      <li key={`g-${i}`}>
        {enlace(grupo, `gn-${i}`, vistos)}
        {papel && <span className="text-ink-dim"> · {papel}</span>}
      </li>
    );
  });
  if (grupos.length > 0) {
    rows.push({ label: "Grupos", value: <ul className="space-y-1">{grupos}</ul> });
  }

  const colegas = lista(rel.colleague);
  if (colegas.length > 0) {
    rows.push({
      label: "Tocó con",
      value: separados(colegas.map((c, i) => enlace(c, `c-${i}`, vistos))),
    });
  }

  const obras = lista((rel["@reverse"] as Nodo | undefined)?.creator);
  if (obras.length > 0) {
    rows.push({
      label: "Obras",
      value: (
        <ul className="space-y-1">
          {obras.map((o, i) => {
            const lugar = lista(o.locationCreated)[0];
            const donde = lugar ? texto(lugar.name) : null;
            const dentro = lugar ? lista(lugar.containedInPlace)[0] : undefined;
            const extra = [donde, dentro ? texto(dentro.name) : null, texto(o.dateCreated)]
              .filter(Boolean).join(", ");
            return (
              <li key={`o-${i}`}>
                {texto(o.name)}
                {extra && <span className="text-ink-dim"> · {extra}</span>}
              </li>
            );
          })}
        </ul>
      ),
    });
  }

  if (detail.other_bands.length > 0) {
    rows.push({
      label: "Otros proyectos",
      value: (
        <ul className="space-y-1">
          {detail.other_bands.map((b) => (
            <li key={b.wikidata_id}>
              {b.internal_url && !primeraVez(vistos, b.internal_url) ? (
                <span>{b.name}</span>
              ) : b.internal_url ? (
                <Link
                  href={b.internal_url}
                  data-cursor="hover"
                  className="text-accent hover:underline"
                >
                  {b.name}
                </Link>
              ) : b.wikipedia_url ? (
                <a
                  href={b.wikipedia_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-cursor="hover"
                  className="text-accent hover:underline"
                >
                  {b.name} ↗
                </a>
              ) : (
                <span className="text-ink-dim">{b.name}</span>
              )}
            </li>
          ))}
        </ul>
      ),
    });
  }

  if (rows.length === 0) return null;

  return (
    <section className="my-12 border border-divider">
      <table className="w-full border-collapse text-left">
        <caption className="caption-top px-5 py-3 font-mono text-[11px] tracking-[3px] uppercase text-accent border-b border-divider text-left">
          Ficha técnica
        </caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-divider last:border-b-0">
              <th
                scope="row"
                className="align-top w-[40%] md:w-[28%] px-5 py-4 font-mono text-[10px] md:text-[11px] tracking-[2px] uppercase text-ink-faint font-normal"
              >
                {row.label}
              </th>
              <td className="align-top px-5 py-4 font-serif text-lg text-ink leading-relaxed">
                {row.value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
