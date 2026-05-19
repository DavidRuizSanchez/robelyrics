import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import SubscriberListWithActions from "./SubscriberListWithActions";

type AdminSubscriberItem = {
  id: number;
  email: string;
  status: string;
  source: string | null;
  subscribed_at: string;
  confirmed_at: string | null;
  unsubscribed_at: string | null;
  last_sent_at: string | null;
};

type AdminSubscriberStats = {
  pending: number;
  confirmed: number;
  unsubscribed: number;
  bounced: number;
  total: number;
};

export const metadata = {
  title: "Admin · Suscriptores · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

const STATUSES = [
  { value: "all", label: "todos" },
  { value: "pending", label: "pendientes" },
  { value: "confirmed", label: "confirmados" },
  { value: "unsubscribed", label: "bajas" },
  { value: "bounced", label: "rebotados" },
];

export default async function AdminSubscribersPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; q?: string }>;
}) {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/subscribers");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  const { status = "all", q } = await searchParams;
  const query = new URLSearchParams({ status });
  if (q) query.set("q", q);

  const [items, stats] = await Promise.all([
    apiFetch<AdminSubscriberItem[]>(`/admin/subscribers?${query.toString()}`),
    apiFetch<AdminSubscriberStats>("/admin/subscribers/stats"),
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
          Suscriptores de la newsletter
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-3 max-w-2xl">
          Estado y mantenimiento de la lista. Reenvía confirmación a los que
          dejaron el doble opt-in a medias, marca rebotados, depura.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-8 text-center">
          <Stat label="total" value={stats.total} />
          <Stat label="confirmados" value={stats.confirmed} />
          <Stat label="pendientes" value={stats.pending} />
          <Stat label="bajas" value={stats.unsubscribed} />
          <Stat label="rebotados" value={stats.bounced} />
        </div>
      </header>

      <div className="flex flex-wrap gap-x-4 gap-y-2 mb-8 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint border-b border-divider pb-4">
        <span>filtro estado:</span>
        {STATUSES.map((s) => (
          <Link
            key={s.value}
            href={`/biblioteca/admin/subscribers?status=${s.value}`}
            data-cursor="hover"
            className={`hover:text-accent ${status === s.value ? "text-accent" : ""}`}
          >
            {s.label}
          </Link>
        ))}
      </div>

      <SubscriberListWithActions items={items} />
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
