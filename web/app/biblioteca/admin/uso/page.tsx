import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";

export const dynamic = "force-dynamic";

type FeatureCount = { feature: string; total: number };
type UsageSummary = {
  days: number;
  by_feature: FeatureCount[];
  consultorio_total: number;
  consultorio_sin_respuesta: number;
};
type TopQuery = { query: string; veces: number };

const FEATURE_LABEL: Record<string, string> = {
  consultorio: "Pregúntale al viento",
  search: "Buscador semántico",
  complete: "Completar",
  mood: "Listas por mood",
};

export default async function AdminUsoPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/uso");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let summary: UsageSummary | null = null;
  let topConsultorio: TopQuery[] = [];
  let topSearch: TopQuery[] = [];
  try {
    [summary, topConsultorio, topSearch] = await Promise.all([
      apiFetch<UsageSummary>("/admin/usage/summary?days=30"),
      apiFetch<TopQuery[]>("/admin/usage/top?feature=consultorio&days=30&limit=15"),
      apiFetch<TopQuery[]>("/admin/usage/top?feature=search&days=30&limit=15"),
    ]);
  } catch {
    // vacío
  }

  const noResRate =
    summary && summary.consultorio_total > 0
      ? Math.round((summary.consultorio_sin_respuesta / summary.consultorio_total) * 100)
      : 0;

  return (
    <div className="max-w-[820px] space-y-12">
      <section>
        <h2 className="font-mono text-[11px] tracking-[3px] uppercase text-accent mb-1">
          Uso de features · últimos 30 días
        </h2>
        <p className="font-serif italic text-ink-dim text-sm mb-5">
          Cuánto se usa cada cosa y qué pregunta la gente. El ratio agregado también está en GA4.
        </p>
        {!summary || summary.by_feature.length === 0 ? (
          <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
            Aún no hay datos de uso registrados.
          </p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {summary.by_feature.map((f) => (
              <div key={f.feature} className="border border-divider/60 p-4">
                <div className="font-serif text-3xl text-ink">{f.total}</div>
                <div className="font-mono text-[10px] tracking-[1px] uppercase text-ink-dim mt-1">
                  {FEATURE_LABEL[f.feature] || f.feature}
                </div>
              </div>
            ))}
          </div>
        )}
        {summary && summary.consultorio_total > 0 && (
          <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint mt-4">
            Consultorio sin respuesta (huecos de contenido): {summary.consultorio_sin_respuesta} de{" "}
            {summary.consultorio_total} ({noResRate}%)
          </p>
        )}
      </section>

      <section className="grid md:grid-cols-2 gap-10">
        <div>
          <h3 className="font-mono text-[10px] tracking-[2px] uppercase text-accent mb-3">
            Top preguntas al viento
          </h3>
          <TopList items={topConsultorio} />
        </div>
        <div>
          <h3 className="font-mono text-[10px] tracking-[2px] uppercase text-accent mb-3">
            Top búsquedas
          </h3>
          <TopList items={topSearch} />
        </div>
      </section>
    </div>
  );
}

function TopList({ items }: { items: TopQuery[] }) {
  if (items.length === 0) {
    return (
      <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">Nada aún.</p>
    );
  }
  return (
    <ul className="space-y-1.5">
      {items.map((q, i) => (
        <li key={i} className="flex justify-between gap-3 border-b border-divider/40 pb-1.5">
          <span className="font-serif text-[15px] text-ink truncate">{q.query}</span>
          <span className="font-mono text-[10px] tracking-[1px] text-ink-faint shrink-0">×{q.veces}</span>
        </li>
      ))}
    </ul>
  );
}
