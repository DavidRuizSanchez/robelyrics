import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import BlogPlanner from "./BlogPlanner";
import UrlIngestForm from "./UrlIngestForm";
import PostQueues, { agruparPorEstado } from "./PostQueues";

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
    <main className="px-5 md:px-14 py-8 md:py-10 max-w-[1100px] mx-auto">
      <header className="mb-10">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          panel admin
        </p>
        <h1 className="font-serif text-4xl md:text-5xl text-ink leading-[1.1] tracking-[-0.5px]">
          Blog · flujo editorial
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-3 max-w-2xl">
          Dos colas distintas: las <b>entradas</b> son textos ya escritos que
          esperan tu decisión; las <b>ideas</b> son temas aún sin escribir. Tope
          de 4 publicaciones por semana.
        </p>

        {/* Dos filas etiquetadas, no seis contadores seguidos: «por validar 0»
            (ideas) y «en revisión 13» (entradas) parecían lo mismo, así que un
            0 arriba se leía como «no hay nada que hacer» teniendo 13 abajo. */}
        <div className="mt-8">
          <p className="font-mono text-[9px] tracking-[3px] uppercase text-accent mb-2">
            entradas · textos escritos
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <Stat label="esperan decisión" value={nPost("pending_review")} href="#entradas-revision" />
            <Stat label="programadas" value={nPost("scheduled")} href="#entradas-programadas" />
            <Stat label="publicadas" value={nPost("published")} />
            <Stat label="rechazadas" value={nPost("rejected")} href="#entradas-rechazadas" />
          </div>
          <p className="font-mono text-[9px] tracking-[3px] uppercase text-ink-faint mt-6 mb-2">
            ideas · temas sin escribir
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <Stat label="por validar" value={stats.proposed} href="#ideas" />
            <Stat label="aprobadas" value={stats.approved} href="#ideas" />
            <Stat label="programadas" value={stats.scheduled} href="#ideas" />
            <Stat label="descartadas" value={stats.discarded} href="#ideas" />
          </div>
        </div>

        <UrlIngestForm />
      </header>

      {/* Primero lo que espera decisión; las ideas, después. Al revés, las
          entradas quedaban al fondo detrás de 320 descartadas. */}
      <PostQueues posts={allPosts} />

      <section id="ideas" className="mt-16 scroll-mt-8">
        <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-1">
          Ideas · temas sin escribir
        </h2>
        <p className="font-serif italic text-ink-dim text-sm mb-8">
          El banco de temas. Aquí no hay nada escrito todavía: validas la idea y
          eliges cuándo se convierte en entrada.
        </p>
        <BlogPlanner
          proposed={proposed}
          approved={approved}
          scheduled={scheduled}
          discarded={discarded}
          discardedTotal={stats.discarded}
        />
      </section>
    </main>
  );
}

function Stat({
  label,
  value,
  href,
}: {
  label: string;
  value: number;
  href?: string;
}) {
  const cuerpo = (
    <>
      <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
        {label}
      </p>
      <p className="font-serif text-3xl text-ink mt-1">{value}</p>
    </>
  );
  // Con ancla, el contador LLEVA a su cola: el salto de la cabecera a la
  // sección era todo el problema cuando la página mide varias pantallas.
  return href ? (
    <a
      href={href}
      data-cursor="hover"
      className="block border border-divider hover:border-accent py-4 transition-colors"
    >
      {cuerpo}
    </a>
  ) : (
    <div className="border border-divider py-4">{cuerpo}</div>
  );
}
