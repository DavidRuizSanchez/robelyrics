import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import ErrataRow, { type ErrataItem } from "./ErrataRow";

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
    <div className="max-w-[820px] space-y-12">
      <section>
        <h2 className="font-mono text-[11px] tracking-[3px] uppercase text-accent mb-1">
          Erratas por revisar
        </h2>
        <p className="font-serif italic text-ink-dim text-sm mb-5">
          El consenso resuelve solo lo que puede; aquí queda lo que necesita tu criterio.
        </p>
        {queue.length === 0 ? (
          <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
            Nada pendiente. Todo al día.
          </p>
        ) : (
          <div>
            {queue.map((it) => (
              <ErrataRow key={it.id} item={it} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="font-mono text-[11px] tracking-[3px] uppercase text-accent mb-1">
          Auto-correcciones (auditoría)
        </h2>
        <p className="font-serif italic text-ink-dim text-sm mb-5">
          Lo que el consenso corrigió solo. Trazable y reversible.
        </p>
        {audit.length === 0 ? (
          <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
            Aún no hay auto-correcciones registradas.
          </p>
        ) : (
          <div className="space-y-3">
            {audit.map((a) => (
              <div key={a.id} className="border-b border-divider/40 pb-3 font-serif text-[14px] text-ink">
                <span className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint mr-2">
                  {a.claim_kind} · conf {a.confidence.toFixed(2)}
                  {a.reverted ? " · revertida" : ""}
                </span>
                {a.old_value && a.new_value && (
                  <span>
                    <span className="text-ink-dim line-through">{a.old_value}</span>{" "}
                    <span className="text-accent">→ {a.new_value}</span>
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
