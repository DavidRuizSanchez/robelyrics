import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import { CLAIM_KIND } from "@/lib/admin/labels";
import ErrataRow, { type ErrataItem } from "./ErrataRow";
import { AdminPage, EmptyState, Section, StatusBadge, Table, cx, tdClass } from "@/components/admin/ui";

export const dynamic = "force-dynamic";

type AuditItem = {
  id: number;
  claim_kind: string;
  song_id: number | null;
  old_value: string | null;
  new_value: string | null;
  verdict: string;
  confidence: number;
  auto_applied: boolean;
  reverted: boolean;
  checked_at: string;
};

export default async function AdminErratasPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/erratas");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let queue: ErrataItem[] = [];
  let audit: AuditItem[] = [];
  try {
    [queue, audit] = await Promise.all([
      apiFetch<ErrataItem[]>("/errata/admin"),
      apiFetch<AuditItem[]>("/errata/admin/audit?only_applied=true"),
    ]);
  } catch {
    // silencioso: la página muestra estado vacío
  }

  return (
    <AdminPage
      title="Erratas"
      intro="Avisos de gente que ha visto algo mal. El sistema arregla solo lo que puede comprobar en fuentes; aquí queda lo que necesita tu criterio."
    >
      <Section title="Por revisar" count={queue.length}>
        {queue.length === 0 ? (
          <EmptyState>Nada pendiente. Todo al día.</EmptyState>
        ) : (
          <div className="space-y-3">
            {queue.map((it) => (
              <ErrataRow key={it.id} item={it} />
            ))}
          </div>
        )}
      </Section>

      <Section
        title="Corregidas automáticamente"
        count={audit.length}
        help="Lo que el sistema corrigió solo porque varias fuentes coincidían. Queda registrado y se puede revertir."
      >
        {audit.length === 0 ? (
          <EmptyState>Aún no hay correcciones automáticas registradas.</EmptyState>
        ) : (
          <Table head={["Qué", "Antes", "Ahora", "Confianza", "Estado"]}>
            {audit.map((a) => (
              <tr key={a.id}>
                <td className={tdClass}>{CLAIM_KIND[a.claim_kind] ?? a.claim_kind}</td>
                <td className={cx(tdClass, "font-serif text-ink-dim line-through")}>{a.old_value ?? "—"}</td>
                <td className={cx(tdClass, "font-serif text-ink")}>{a.new_value ?? "—"}</td>
                <td className={cx(tdClass, "font-mono")}>{a.confidence.toFixed(2)}</td>
                <td className={tdClass}>
                  {a.reverted ? <StatusBadge>Revertida</StatusBadge> : <StatusBadge tone="ok">Aplicada</StatusBadge>}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>
    </AdminPage>
  );
}
