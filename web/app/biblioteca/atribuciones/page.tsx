import Link from "next/link";
import { apiFetch } from "@/lib/api";

type SourceListItem = {
  id: number;
  kind: string;
  url: string;
  title: string | null;
  author: string | null;
  published_at: string | null;
};

type SourceListOut = {
  total: number;
  items: SourceListItem[];
};

const KIND_LABELS: Record<string, string> = {
  blog: "Blogs fan",
  forum: "Foros",
  youtube_transcript: "Transcripts de YouTube",
  youtube_comment: "Comentarios de YouTube",
  genius_annotation: "Anotaciones de Genius",
  manual: "Aportaciones manuales",
  book: "Libros",
  thesis: "Tesis y papers",
};

const KIND_LICENSES: Record<string, string> = {
  genius_annotation: "CC-BY-NC-SA 3.0 · obra original de cada anotador en Genius",
  blog: "Cita amparada (LPI 32) · ©de cada autor",
  forum: "Cita amparada (LPI 32) · ©de cada autor",
  youtube_transcript: "Cita amparada · ©del canal/autor del vídeo",
  youtube_comment: "Cita amparada · ©del autor del comentario",
  manual: "Aportación curada por la comunidad de Entre Interiores",
  book: "Cita amparada (LPI 32) · ©del autor / editorial",
  thesis: "Cita amparada (LPI 32) · ©del autor / institución",
};

export const metadata = {
  title: "Atribuciones · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function AtribucionesPage() {
  // Carga las primeras N fuentes. La paginación completa puede añadirse en el
  // futuro; con 323 fuentes y server-render rápido, mostrar 200 de un tirón
  // es suficiente para la página de atribuciones.
  let data: SourceListOut = { total: 0, items: [] };
  try {
    data = await apiFetch<SourceListOut>("/sources?limit=500");
  } catch {
    /* ignoramos: render con datos vacíos */
  }

  // Agrupar por kind
  const byKind = new Map<string, SourceListItem[]>();
  for (const item of data.items) {
    const list = byKind.get(item.kind) ?? [];
    list.push(item);
    byKind.set(item.kind, list);
  }
  const orderedKinds = Array.from(byKind.keys()).sort((a, b) => {
    // Genius primero (más relevante para la atribución legal CC-BY-NC-SA),
    // luego por número de fuentes desc.
    if (a === "genius_annotation") return -1;
    if (b === "genius_annotation") return 1;
    return (byKind.get(b)?.length ?? 0) - (byKind.get(a)?.length ?? 0);
  });

  return (
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-3xl mx-auto">
      <Link
        href="/biblioteca"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← biblioteca
      </Link>

      <header className="mt-6 mb-12">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          atribuciones
        </p>
        <h1 className="font-serif text-4xl md:text-5xl text-ink mb-5 leading-[1.1] tracking-[-0.5px]">
          Las voces que han hecho posible este cancionero
        </h1>
        <p className="font-serif italic text-ink-dim text-lg leading-relaxed max-w-xl">
          Cada interpretación que ves en la biblioteca tiene detrás a
          aficionados que escribieron, comentaron, debatieron, transcribieron.
          Aquí están todas las fuentes con su atribución y enlace al original.
        </p>
      </header>

      <section className="mb-12 border-l-2 border-accent/40 pl-5">
        <h2 className="font-mono text-[10px] tracking-[2px] uppercase text-accent mb-3">
          Licencia del contenido derivado
        </h2>
        <p className="font-serif text-ink leading-relaxed">
          Los análisis fan destilados que se muestran en cada canción son obra
          derivada de las fuentes listadas abajo. En particular, las
          anotaciones de Genius están licenciadas{" "}
          <Link
            href="https://creativecommons.org/licenses/by-nc-sa/3.0/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent underline"
          >
            CC-BY-NC-SA 3.0
          </Link>
          . Por compatibilidad, los destilados aquí publicados quedan también
          disponibles bajo la misma licencia: uso libre con atribución, no
          comercial, y obras derivadas bajo la misma licencia.
        </p>
      </section>

      <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-6">
        {data.total} fuentes catalogadas
      </p>

      <div className="space-y-12">
        {orderedKinds.map((kind) => {
          const items = byKind.get(kind) ?? [];
          return (
            <section key={kind}>
              <h2 className="font-serif text-2xl text-ink mb-1">
                {KIND_LABELS[kind] || kind}{" "}
                <span className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint align-middle">
                  · {items.length}
                </span>
              </h2>
              <p className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint mb-4">
                {KIND_LICENSES[kind] || "©de su autor"}
              </p>
              <ul className="divide-y divide-divider border-t border-divider">
                {items.map((s) => (
                  <li key={s.id} className="py-3">
                    <Link
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block group"
                    >
                      <p className="font-serif text-ink group-hover:text-accent transition-colors leading-snug">
                        {s.title || s.url}
                      </p>
                      <p className="font-mono text-[10px] tracking-[1.5px] text-ink-faint mt-1">
                        {s.author || "anónimo"}
                        {s.published_at &&
                          ` · ${new Date(s.published_at).toLocaleDateString("es-ES")}`}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </main>
  );
}
