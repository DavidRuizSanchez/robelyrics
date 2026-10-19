import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import SubscriberListWithActions from "./SubscriberListWithActions";
import {
  AdminPage,
  Metric,
  MetricGrid,
  buttonClass,
  cx,
  filterClass,
  inputClass,
} from "@/components/admin/ui";

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
  { value: "all", label: "Todos" },
  { value: "pending", label: "Sin confirmar" },
  { value: "confirmed", label: "Confirmados" },
  { value: "unsubscribed", label: "Bajas" },
  { value: "bounced", label: "Rebotan" },
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
    <AdminPage
      title="Suscriptores"
      intro="La lista de la newsletter. Solo reciben correo los confirmados: los «sin confirmar» dejaron el doble opt-in a medias."
    >
      <MetricGrid>
        <Metric label="Confirmados (reciben correo)" value={stats.confirmed} tone="ok" />
        <Metric label="Sin confirmar" value={stats.pending} tone={stats.pending > 0 ? "warn" : "neutral"} />
        <Metric label="Bajas" value={stats.unsubscribed} />
        <Metric label="Rebotan" value={stats.bounced} tone={stats.bounced > 0 ? "danger" : "neutral"} />
      </MetricGrid>
      <p className="-mt-6 text-sm text-ink-faint">Total histórico: {stats.total}.</p>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-2" aria-label="Filtrar por estado">
          {STATUSES.map((s) => (
            <Link
              key={s.value}
              href={`/biblioteca/admin/subscribers?status=${s.value}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
              aria-current={status === s.value ? "page" : undefined}
              className={filterClass(status === s.value)}
            >
              {s.label}
            </Link>
          ))}
        </div>
        <form method="get" className="flex items-center gap-2 sm:ml-auto" role="search">
          <input type="hidden" name="status" value={status} />
          <label htmlFor="q" className="sr-only">
            Buscar por correo
          </label>
          <input
            id="q"
            name="q"
            defaultValue={q ?? ""}
            placeholder="Buscar por correo…"
            className={cx(inputClass, "w-56")}
          />
          <button type="submit" className={buttonClass("secondary", "sm")}>
            Buscar
          </button>
        </form>
      </div>

      <SubscriberListWithActions items={items} />
    </AdminPage>
  );
}
