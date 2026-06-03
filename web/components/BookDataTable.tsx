import type { ReactNode } from "react";

type BookDataTableDetail = {
  authors: string[];
  year: number | null;
  publisher: string | null;
  isbn: string | null;
  pages: number | null;
  language: string;
  kind: string;
  availability: string;
};

const KIND_LABEL: Record<string, string> = {
  biografia: "Biografía",
  ensayo: "Ensayo",
  novela: "Novela",
  monografico: "Monográfico",
  poesia: "Poesía",
};

const AVAILABILITY_LABEL: Record<string, string> = {
  new: "A la venta (nuevo)",
  secondhand: "Disponible de segunda mano",
  out_of_print: "Descatalogado",
};

const LANGUAGE_LABEL: Record<string, string> = {
  es: "Español",
  en: "Inglés",
};

type Row = { label: string; value: ReactNode };

export default function BookDataTable({
  detail,
}: {
  detail: BookDataTableDetail;
}) {
  const rows: Row[] = [];

  if (detail.authors.length > 0) {
    rows.push({
      label: detail.authors.length > 1 ? "Autores" : "Autor",
      value: detail.authors.join(" · "),
    });
  }
  if (detail.year) rows.push({ label: "Año", value: String(detail.year) });
  if (detail.publisher) rows.push({ label: "Editorial", value: detail.publisher });
  rows.push({ label: "Tipo", value: KIND_LABEL[detail.kind] || detail.kind });
  if (detail.pages) rows.push({ label: "Páginas", value: String(detail.pages) });
  if (detail.isbn) rows.push({ label: "ISBN", value: detail.isbn });
  rows.push({
    label: "Idioma",
    value: LANGUAGE_LABEL[detail.language] || detail.language,
  });
  rows.push({
    label: "Disponibilidad",
    value: AVAILABILITY_LABEL[detail.availability] || detail.availability,
  });

  if (rows.length === 0) return null;

  return (
    <section className="my-12 border border-divider">
      <table className="w-full border-collapse text-left">
        <caption className="caption-top px-5 py-3 font-mono text-[11px] tracking-[3px] uppercase text-accent border-b border-divider text-left">
          Ficha del libro
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
