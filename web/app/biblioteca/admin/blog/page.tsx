import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import BlogPlanner from "./BlogPlanner";
import UrlIngestForm from "./UrlIngestForm";
import PostListWithActions from "../posts/PostListWithActions";

export type ProposalKeyword = {
  keyword: string;
  volume: number;
  cpc: number | null;
  competition: number | null;
};

export type ProposalItem = {
  id: number;
  kind: string;
  source_type: string | null;
  source_id: number | null;
  title: string;
  angle: string | null;
  status: string;
  scheduled_for: string | null;
  recommended_for: string | null;
  event_date: string | null;
  source_url: string | null;
  source_name: string | null;
  has_body: boolean;
  keywords: ProposalKeyword[];
  keyword_volume: number;
  target_keyword: string | null;
  search_volume: number | null;
  is_longtail: boolean;
  signal_source: string | null;
  created_at: string;
};

type ProposalStats = {
  proposed: number;
  approved: number;
  scheduled: number;
  used: number;
  discarded: number;
  by_kind: Record<string, Record<string, number>>;
};

type AdminPostItem = {
  id: number;
  slug: string;
  kind: string;
  status: string;
  title: string;
  excerpt: string | null;
  source_url: string | null;
  source_name: string | null;
  created_at: string;
  published_at: string | null;
  scheduled_for: string | null;
};

export const metadata = {
  title: "Admin · Blog · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function AdminBlogPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/blog");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  const [proposed, approved, scheduled, discarded, stats, pendingPosts] =
    await Promise.all([
      apiFetch<ProposalItem[]>("/admin/proposals?status=proposed"),
      apiFetch<ProposalItem[]>("/admin/proposals?status=approved"),
      apiFetch<ProposalItem[]>("/admin/proposals?status=scheduled"),
      apiFetch<ProposalItem[]>("/admin/proposals?status=discarded"),
      apiFetch<ProposalStats>("/admin/proposals/stats"),
      apiFetch<AdminPostItem[]>("/admin/posts?status=pending_review"),
    ]);

  return (
    <main className="px-5 md:px-14 py-8 md:py-10 max-w-[1100px] mx-auto">
      <header className="mb-10">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          panel admin
        </p>
        <h1 className="font-serif text-4xl md:text-5xl text-ink leading-[1.1] tracking-[-0.5px]">
          Blog · flujo editorial
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-3 max-w-2xl">
          Un solo sitio: valida las propuestas (aprobar o rechazar), y luego
          en el calendario decide cuándo publicarlas. Tope de 4 por semana.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-8 text-center">
          <Stat label="por validar" value={stats.proposed} />
          <Stat label="aprobadas" value={stats.approved} />
          <Stat label="programadas" value={stats.scheduled} />
          <Stat label="publicadas" value={stats.used} />
          <Stat label="descartadas" value={stats.discarded} />
        </div>

        <UrlIngestForm />
      </header>

      <BlogPlanner
        proposed={proposed}
        approved={approved}
        scheduled={scheduled}
        discarded={discarded}
      />

      {pendingPosts.length > 0 && (
        <section className="mt-16">
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
            Entradas a revisar (editorial manual)
          </h2>
          <p className="font-serif italic text-ink-dim text-sm mb-5">
            Posts creados a mano o por spotlight. Publica, programa o rechaza.
          </p>
          <PostListWithActions items={pendingPosts} />
        </section>
      )}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-divider py-4">
      <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
        {label}
      </p>
      <p className="font-serif text-3xl text-ink mt-1">{value}</p>
    </div>
  );
}
