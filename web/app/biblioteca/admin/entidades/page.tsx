import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import { AdminPage, Callout, EmptyState, Section } from "@/components/admin/ui";
import { PropuestaRow, RelacionRow, type Propuesta, type RelacionPendiente } from "./EntidadRow";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Relaciones y entidades · Admin · Entre Interiores",
  robots: { index: false, follow: false },
};

type Cola = {
  cuenta: Record<string, number>;
  propuestas: Record<string, Propuesta[]>;
  relaciones_pendientes: RelacionPendiente[];
  n_relaciones_pendientes: number;
};

export default async function AdminEntidadesPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/entidades");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let cola: Cola = { cuenta: {}, propuestas: {}, relaciones_pendientes: [], n_relaciones_pendientes: 0 };
  try {
    cola = await apiFetch<Cola>("/admin/entidades");
  } catch {
    // silencioso: estado vacío
  }
  const lista = (estado: string) => cola.propuestas[estado] ?? [];
  const n = (estado: string) => cola.cuenta[estado] ?? 0;

  return (
    <AdminPage
      title="Relaciones y entidades"
      intro="Lo que sale de cruzar nuestras entidades con Wikidata, MusicBrainz y nuestros datos. Las relaciones con un T1 o dos T2 ya están publicadas; aquí queda lo que necesita tu criterio."
    >
      <Callout tone="info" title="Cómo se decide">
        Una relación pendiente es verdad o no lo es: aprobarla la publica en las dos fichas. Una
        entidad propuesta es la otra punta de una relación sin página propia: aprobarla significa
        «hazle ficha», no la publica.
      </Callout>

      <Section
        title={`Relaciones pendientes (${cola.n_relaciones_pendientes})`}
        help="Les falta una segunda fuente de prensa: por ejemplo, conciertos que solo recoge un archivo de aficionados."
      >
        {cola.relaciones_pendientes.length === 0 ? (
          <EmptyState>Nada pendiente.</EmptyState>
        ) : (
          <div className="space-y-3">
            {cola.relaciones_pendientes.map((r) => (
              <RelacionRow key={r.id} item={r} />
            ))}
          </div>
        )}
      </Section>

      <Section
        title={`Entidades propuestas (${n("propuesta")})`}
        help="Ordenadas por cuánto material hay en el corpus para escribir su ficha sin inventar."
      >
        {lista("propuesta").length === 0 ? (
          <EmptyState>No hay propuestas nuevas.</EmptyState>
        ) : (
          <div className="space-y-3">
            {lista("propuesta").map((p) => (
              <PropuestaRow key={p.id} item={p} />
            ))}
          </div>
        )}
      </Section>

      <Section title={`Aprobadas, a falta de ficha (${n("aprobada")})`}>
        {lista("aprobada").length === 0 ? (
          <EmptyState>Ninguna.</EmptyState>
        ) : (
          <div className="space-y-3">
            {lista("aprobada").map((p) => (
              <PropuestaRow key={p.id} item={p} />
            ))}
          </div>
        )}
      </Section>

      <Section title={`Descartadas (${n("descartada")})`}>
        {lista("descartada").length === 0 ? (
          <EmptyState>Ninguna.</EmptyState>
        ) : (
          <div className="space-y-3">
            {lista("descartada").map((p) => (
              <PropuestaRow key={p.id} item={p} />
            ))}
          </div>
        )}
      </Section>
    </AdminPage>
  );
}
