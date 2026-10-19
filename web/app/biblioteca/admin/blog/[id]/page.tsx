import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiFetch, ApiError } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import ProposalActions from "./ProposalActions";
import TitleEditor from "./TitleEditor";
import { Card, Data, Eyebrow, StatusBadge } from "@/components/admin/ui";
import { PROPOSAL_STATUS, etiqueta, kindLabel } from "@/lib/admin/labels";
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

  const st = etiqueta(PROPOSAL_STATUS, p.status);
  const kws = (p.keywords ?? []).slice().sort((a, b) => b.volume - a.volume);

  return (
    <main className="px-5 md:px-14 py-8 md:py-10 max-w-[820px] mx-auto">
      <Link href="/biblioteca/admin/blog" className="text-sm text-ink-dim hover:text-ink">
        ← Volver al blog
      </Link>

      <header className="mt-6 mb-6">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-ink-dim">
          <span className="font-mono text-ink-faint">#{p.id}</span>
          <span>Idea · {kindLabel(p.kind)}</span>
          <StatusBadge tone={st.tone} title={st.hint}>
            {st.label}
          </StatusBadge>
        </div>
        {p.status === "used" || p.status === "discarded" ? (
          <h1 className="font-serif text-3xl md:text-4xl text-ink leading-[1.15]">{p.title}</h1>
        ) : (
          <TitleEditor id={p.id} initialTitle={p.title} />
        )}
        {p.angle && <p className="font-serif italic text-ink-dim text-lg mt-3">{p.angle}</p>}
      </header>

      <Card className="mb-6">
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-[max-content_1fr] text-sm">
          {p.event_date && (
            <>
              <dt className="text-ink-faint">Evento</dt>
              <dd className="text-ink">
                {p.event_date}
                {p.recommended_for ? ` · se sugiere publicar el ${p.recommended_for}` : ""}
              </dd>
            </>
          )}
          {p.target_keyword && (
            <>
              <dt className="text-ink-faint">Búsqueda objetivo</dt>
              <dd>
                <Data>{p.target_keyword}</Data>
                {p.search_volume ? (
                  <span className="text-ink-dim"> · {p.search_volume.toLocaleString("es-ES")} al mes</span>
                ) : null}
                {p.is_longtail ? <span className="text-ink-dim"> · long-tail</span> : null}
              </dd>
            </>
          )}
          {kws.length > 0 && (
            <>
              <dt className="text-ink-faint">Otras búsquedas</dt>
              <dd className="flex flex-wrap gap-1.5">
                {kws.slice(0, 10).map((k) => (
                  <span key={k.keyword} className="rounded border border-divider px-1.5 py-0.5 font-mono text-xs text-ink">
                    {k.keyword} <span className="text-ink-faint">{k.volume.toLocaleString("es-ES")}</span>
                  </span>
                ))}
                {kws.length > 10 && <span className="text-xs text-ink-faint">+{kws.length - 10} más</span>}
              </dd>
            </>
          )}
          {p.source_url && (
            <>
              <dt className="text-ink-faint">Fuente</dt>
              <dd>
                <a
                  href={p.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline break-all"
                >
                  {p.source_name || p.source_url} ↗
                </a>
              </dd>
            </>
          )}
        </dl>
        <ProposalActions id={p.id} status={p.status} />
      </Card>

      <section className="mt-10 border-t border-divider pt-8">
        <Eyebrow className="mb-4">{p.body_md ? "Borrador" : "Estado del borrador"}</Eyebrow>
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
