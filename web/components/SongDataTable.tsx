import type { ReactNode } from "react";
import Link from "next/link";
import type {
  PublicArtistOut,
  PublicAlbumOut,
  PublicLineupMember,
} from "@/lib/types";

type SongDataTableDetail = {
  track_number: number | null;
  artist: PublicArtistOut;
  album: PublicAlbumOut;
  youtube_duration_sec: number | null;
  lineup: PublicLineupMember[];
};

function formatDuration(sec: number | null): string | null {
  if (sec == null || sec <= 0) return null;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

type Row = {
  label: string;
  /** Contenido de la celda de valor (texto o JSX). */
  value: ReactNode;
};

export default function SongDataTable({
  detail,
}: {
  detail: SongDataTableDetail;
}) {
  const rows: Row[] = [];

  rows.push({
    label: "Disco",
    value: (
      <Link
        href={`/${detail.artist.slug}/${detail.album.slug}`}
        data-cursor="hover"
        className="text-accent hover:underline"
      >
        {detail.album.title}
      </Link>
    ),
  });

  if (detail.album.year) {
    rows.push({ label: "Año", value: String(detail.album.year) });
  }

  if (detail.track_number != null) {
    rows.push({ label: "Pista nº", value: String(detail.track_number) });
  }

  const duration = formatDuration(detail.youtube_duration_sec);
  if (duration) {
    rows.push({ label: "Duración", value: duration });
  }

  if (detail.lineup.length > 0) {
    rows.push({
      label: "Formación de la época",
      value: (
        <>
          <ul className="space-y-1">
            {detail.lineup.map((m) => (
              <li key={m.slug}>
                <Link
                  href={`/personas/${m.slug}`}
                  data-cursor="hover"
                  className="text-accent hover:underline"
                >
                  {m.name}
                </Link>{" "}
                <span className="text-ink-dim">({m.role})</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
            Aproximación según la época
          </p>
        </>
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
