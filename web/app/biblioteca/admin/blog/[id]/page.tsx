import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiFetch, ApiError } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import ProposalActions from "./ProposalActions";
import TitleEditor from "./TitleEditor";
import GenerationStatus from "./GenerationStatus";

type ProposalDetail = {
  id: number;
  kind: string;
  status: string;
  title: string;
  angle: string | null;
  body_md: string | null;
  excerpt: string | null;
  meta_title: string | null;
  meta_description: string | null;
  scheduled_for: string | null;
  recommended_for: string | null;
  event_date: string | null;
  source_url: string | null;
  source_name: string | null;
  target_keyword: string | null;
  search_volume: number | null;
  is_longtail: boolean;
  keywords: { keyword: string; volume: number }[];
};

const KIND_LABEL: Record<string, string> = {
  news: "Noticia",
  anniversary: "Efeméride Robe",
  "album-anniversary": "Aniversario disco",
  spotlight: "Análisis canción",
  evergreen: "Tema de fondo",
};

export const dynamic = "force-dynamic";

export default async function ProposalReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect(`/login?from=/biblioteca/admin/blog/${id}`);
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let p: ProposalDetail;
  try {
    p = await apiFetch<ProposalDetail>(`/admin/proposals/${id}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="px-5 md:px-14 py-8 md:py-10 max-w-[820px] mx-auto">
      <Link
        href="/biblioteca/admin/blog"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← volver al panel
      </Link>

      <header className="mt-6 mb-8">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          revisar propuesta · {KIND_LABEL[p.kind] ?? p.kind} · {p.status}
        </p>
        {p.status === "used" || p.status === "discarded" ? (
          <h1 className="font-serif text-3xl md:text-4xl text-ink leading-[1.15]">
            {p.title}
          </h1>
        ) : (
          <TitleEditor id={p.id} initialTitle={p.title} />
        )}
        {p.angle && (
          <p className="font-serif italic text-ink-dim text-lg mt-3">{p.angle}</p>
        )}
        <div className="mt-4 font-mono text-[10px] tracking-[1px] text-ink-faint space-y-1">
          {p.event_date && (
            <p className="text-accent">
              evento: {p.event_date}
              {p.recommended_for ? ` · sugerido publicar ${p.recommended_for}` : ""}
            </p>
          )}
          {p.target_keyword && (
            <p>
              KW objetivo: <span className="text-accent">{p.target_keyword}</span>
              {p.search_volume ? ` · ${p.search_volume}/mes` : ""}
              {p.is_longtail ? " · long-tail" : ""}
            </p>
          )}
          {p.keywords?.length > 0 && (
            <p>
              keywords:{" "}
              {p.keywords
                .slice()
                .sort((a, b) => b.volume - a.volume)
                .slice(0, 10)
                .map((k) => `${k.keyword} (${k.volume})`)
                .join(" · ")}
            </p>
          )}
          {p.source_url && (
            <p>
              fuente:{" "}
              <a
                href={p.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                {p.source_name || p.source_url} ↗
              </a>
            </p>
          )}
        </div>
      </header>

      <ProposalActions id={p.id} status={p.status} />

      <section className="mt-10 border-t border-divider pt-8">
        {p.body_md ? (
          <article className="prose-ei">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{p.body_md}</ReactMarkdown>
          </article>
        ) : (
          <GenerationStatus status={p.status} kind={p.kind} />
        )}
      </section>
    </main>
  );
}
