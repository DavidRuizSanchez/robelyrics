import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import { AdminPage, Eyebrow, Metric, MetricGrid } from "@/components/admin/ui";
import BlogPlanner from "./BlogPlanner";
import UrlIngestForm from "./UrlIngestForm";
import PostQueues, { agruparPorEstado } from "./PostQueues";

export type ProposalKeyword = {
  keyword: string;
  volume: number;
  cpc: number | null;
  competition: number | null;
  // Desactivada a mano (o fundida con una página: `merged` lleva la ruta).
  excluded?: boolean;
  merged?: string;
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
  force_publish: boolean;
  has_video: boolean;
  source_url: string | null;
  source_name: string | null;
  has_body: boolean;
  keywords: ProposalKeyword[];
  keyword_volume: number;
  target_keyword: string | null;
  search_volume: number | null;
  is_longtail: boolean;
  signal_source: string | null;
  // ¿Post nuevo o ampliar una página existente? (`content_placement` en la API)
  placement: Placement | null;
  placement_headline: string | null;
  placement_options: PlacementOption[];
  placement_groups: PlacementGroup[];
  merge_target: string | null;
  merge_opportunity_id: number | null;
  created_at: string;
};

export type PlacementCandidate = {
  path: string;
  kind: "ficha" | "post" | "code";
  label: string;
  target: string | null;
  gsc_impressions: number;
  gsc_clicks: number;
  gsc_position: number | null;
  gsc_queries: { query: string; impressions: number; position: number | null }[];
  serp_rank: number | null;
  similarity: number | null;
  is_anchor: boolean;
  mergeable: boolean;
  score: number;
};

export type Placement = {
  decision: "ampliar" | "nuevo" | "cubierto";
  confidence: "alta" | "media" | "baja";
  recommended: string | null;
  reasons: string[];
  candidates: PlacementCandidate[];
  competing: string[];
  period: string | null;
  computed_at?: string;
  last_merge?: { path: string; status: string; error: string };
};

// Un grupo del reparto: keywords que van al mismo destino.
export type PlacementGroup = {
  keywords: string[];
  decision: "ampliar" | "nuevo" | "cubierto";
  confidence: "alta" | "media" | "baja";
  recommended: string | null;
  reasons: string[];
  candidates: PlacementCandidate[];
  headline: string;
  options: PlacementOption[];
  // Por qué se eligió el destino (gsc | titulo | semantica | ninguna). Solo en
  // repartos calculados desde que existe; los anteriores no lo traen.
  via?: string[] | null;
};

export type PlacementOption = {
  value: string; // «ficha:12» | «post:7» | «new» | «skip»
  label: string;
  path?: string;
  recommended: boolean;
};

type ProposalStats = {
  proposed: number;
  approved: number;
  scheduled: number;
  used: number;
  discarded: number;
  by_kind: Record<string, Record<string, number>>;
};

export type AdminPostItem = {
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
  days_waiting: number;
  stale: boolean;
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

  const [proposed, approved, scheduled, discarded, stats, allPosts] =
    await Promise.all([
      apiFetch<ProposalItem[]>("/admin/proposals?status=proposed"),
      apiFetch<ProposalItem[]>("/admin/proposals?status=approved"),
      apiFetch<ProposalItem[]>("/admin/proposals?status=scheduled"),
      // Acotadas: son 320 y se pintaban TODAS, unos 25.000 px de papelera por
      // delante de lo que sí esperaba decisión. El contador de la cabecera sigue
      // saliendo de /stats, así que la cifra que se muestra no miente.
      apiFetch<ProposalItem[]>("/admin/proposals?status=discarded&limit=40"),
      apiFetch<ProposalStats>("/admin/proposals/stats"),
      // Todos los estados de una sola llamada: son ~60 filas sin `body_md`. Si
      // algún día las publicadas pasan de ~150, esa cola pedirá su paginación.
      apiFetch<AdminPostItem[]>("/admin/posts?status=all"),
    ]);

  const porEstado = agruparPorEstado(allPosts);
  const nPost = (estado: string) => (porEstado[estado] ?? []).length;

  return (
    <AdminPage
      title="Blog"
      intro={
        <>
          Dos cosas distintas: las <b className="text-ink">entradas</b> son textos ya escritos
          que esperan tu decisión; las <b className="text-ink">ideas</b> son temas que aún no
          se han escrito. Como mucho salen 4 publicaciones por semana.
        </>
      }
    >
      {/* Dos filas etiquetadas, no seis contadores seguidos: «por validar 0»
          (ideas) y «en revisión 13» (entradas) parecían lo mismo, así que un
          0 arriba se leía como «no hay nada que hacer» teniendo 13 abajo. */}
      <div className="space-y-6">
        <div>
          <Eyebrow className="mb-2">Entradas · textos ya escritos</Eyebrow>
          <MetricGrid>
            <Metric
              label="Esperan tu decisión"
              value={nPost("pending_review")}
              tone={nPost("pending_review") > 0 ? "warn" : "neutral"}
              href="#entradas-revision"
            />
            <Metric label="Programadas" value={nPost("scheduled")} href="#entradas-programadas" />
            <Metric label="Publicadas" value={nPost("published")} />
            <Metric label="Rechazadas" value={nPost("rejected")} href="#entradas-rechazadas" />
          </MetricGrid>
        </div>
        <div>
          <Eyebrow className="mb-2">Ideas · temas sin escribir</Eyebrow>
          <MetricGrid>
            <Metric
              label="Por decidir"
              value={stats.proposed}
              tone={stats.proposed > 0 ? "warn" : "neutral"}
              href="#ideas"
            />
            <Metric label="Aprobadas sin fecha" value={stats.approved} href="#ideas" />
            <Metric label="Programadas" value={stats.scheduled} href="#ideas" />
            <Metric label="Descartadas" value={stats.discarded} href="#ideas" />
          </MetricGrid>
        </div>
      </div>

      <UrlIngestForm />

      {/* Primero lo que espera decisión; las ideas, después. Al revés, las
          entradas quedaban al fondo detrás de 320 descartadas. */}
      <PostQueues posts={allPosts} />

      <div id="ideas" className="scroll-mt-28 border-t border-divider pt-10">
        <h2 className="font-serif text-2xl text-ink">Ideas</h2>
        <p className="mt-1 mb-6 text-ink-dim max-w-2xl">
          El banco de temas. Aquí no hay nada escrito todavía: validas la idea y eliges cuándo
          se convierte en entrada.
        </p>
        <BlogPlanner
          proposed={proposed}
          approved={approved}
          scheduled={scheduled}
          discarded={discarded}
          discardedTotal={stats.discarded}
        />
      </div>
    </AdminPage>
  );
}
