import type { ReactNode } from "react";
import Link from "next/link";
import type { PublicAlbumDetail } from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  studio: "Álbum de estudio",
  live: "Álbum en directo",
  compilation: "Recopilatorio",
  ep: "EP",
  single: "Single",
};

const MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  const [, y, mo, d] = m;
  return `${Number(d)} de ${MONTHS[Number(mo) - 1]} de ${y}`;
}

function totalDuration(detail: PublicAlbumDetail): string | null {
  const secs = detail.tracks.reduce(
    (acc, t) => acc + (t.youtube_duration_sec || t.duration_sec || 0),
    0,
  );
  if (secs <= 0) return null;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h} h ${m} min`;
  return `${m}:${String(s).padStart(2, "0")} min`;
}

type Row = { label: string; value: ReactNode };

export default function AlbumDataTable({ detail }: { detail: PublicAlbumDetail }) {
  const rows: Row[] = [];

  rows.push({
    label: "Artista",
    value: (
      <Link
        href={`/${detail.artist.slug}`}
        data-cursor="hover"
        className="text-accent hover:underline"
      >
        {detail.artist.name}
      </Link>
    ),
  });

  const released = formatDate(detail.release_date);
  rows.push({ label: "Año", value: released || String(detail.year) });

  rows.push({ label: "Tipo", value: KIND_LABEL[detail.kind] || detail.kind });

  if (detail.tracks.length > 0) {
    rows.push({ label: "Canciones", value: String(detail.tracks.length) });
  }

  const dur = totalDuration(detail);
  if (dur) {
    rows.push({ label: "Duración total", value: dur });
  }

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
