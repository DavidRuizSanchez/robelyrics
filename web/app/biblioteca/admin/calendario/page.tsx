import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import CalendarioPlanner from "./CalendarioPlanner";

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
  source_url: string | null;
  source_name: string | null;
  has_body: boolean;
  keywords: ProposalKeyword[];
  keyword_volume: number;
  created_at: string;
};

type ProposalStats = {
  proposed: number;
  scheduled: number;
  used: number;
  discarded: number;
};

export const metadata = {
  title: "Admin · Calendario editorial · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function CalendarioPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/calendario");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  const [proposed, scheduled, stats] = await Promise.all([
    apiFetch<ProposalItem[]>("/admin/proposals?status=proposed"),
    apiFetch<ProposalItem[]>("/admin/proposals?status=scheduled"),
    apiFetch<ProposalStats>("/admin/proposals/stats"),
  ]);

  return (
    <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
      <Link
        href="/biblioteca/admin/sources"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← admin
      </Link>

      <header className="mt-6 mb-10">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          panel admin
        </p>
        <h1 className="font-serif text-4xl md:text-5xl text-ink leading-[1.1] tracking-[-0.5px]">
          Calendario editorial
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-3 max-w-2xl">
          El banco de propuestas. Programa las que quieras publicar, con un
          tope de 2 por semana. Lo que no programes se queda esperando.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8 text-center">
          <Stat label="en el banco" value={stats.proposed} />
          <Stat label="programadas" value={stats.scheduled} />
          <Stat label="publicadas" value={stats.used} />
          <Stat label="descartadas" value={stats.discarded} />
        </div>
      </header>

      <CalendarioPlanner proposed={proposed} scheduled={scheduled} />
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
