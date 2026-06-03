import type { ReactNode } from "react";
import Link from "next/link";

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
};

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

export default function PersonDataTable({
  detail,
}: {
  detail: PersonDataTableDetail;
}) {
  const birth = formatDateEs(detail.birth_date);
  const death = formatDateEs(detail.death_date);

  // "Con Robe/Extremoduro": resumen derivado de las pertenencias al corpus.
  const coreMemberships = detail.memberships.filter((m) =>
    CORE_SLUGS.has(m.artist_slug),
  );
  const coreSummary = coreMemberships
    .map((m) => `${m.role} de ${m.artist_name}${m.era ? ` (${m.era})` : ""}`)
    .join("; ");

  const rows: Row[] = [];

  rows.push({ label: "Nombre real", value: detail.full_name });

  if (detail.stage_name && detail.stage_name !== detail.full_name) {
    rows.push({ label: "Alias", value: detail.stage_name });
  }

  if (birth) {
    rows.push({
      label: "Nacimiento",
      value: `${birth}${detail.birth_place ? ` · ${detail.birth_place}` : ""}`,
    });
  }

  if (death) {
    rows.push({ label: "Fallecimiento", value: death });
  }

  if (detail.instruments.length > 0) {
    rows.push({ label: "Instrumentos", value: detail.instruments.join(" · ") });
  }

  if (detail.occupations.length > 0) {
    rows.push({
      label: "Oficios",
      value: detail.occupations.map((o) => o.name).join(" · "),
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
              <Link
                href={`/${m.artist_slug}`}
                data-cursor="hover"
                className="text-accent hover:underline"
              >
                {m.artist_name}
              </Link>{" "}
              <span className="text-ink-dim">— {describeMembership(m)}</span>
            </li>
          ))}
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
              {b.internal_url ? (
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
