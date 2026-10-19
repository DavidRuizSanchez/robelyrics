import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import OpportunityRow, { type Opportunity } from "./OpportunityRow";
import { AdminPage, Callout, EmptyState, Section } from "@/components/admin/ui";

export const metadata = {
  title: "Admin · Oportunidades SEO · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

// El orden lo manda lo que espera una decisión TUYA. Las que están cociéndose o
// se rompieron van debajo, pero se ven: una cola que solo vive en un correo es
// una cola invisible, y así fue como 24 posts pasaron meses sin que nadie mirara.
const SECCIONES: { status: string; titulo: string; nota: string }[] = [
  {
    status: "drafted",
    titulo: "Borradores listos: esperan tu visto bueno",
    nota: "Esto es lo que se publicaría, tal cual. Nada está en la web todavía.",
  },
  {
    status: "detected",
    titulo: "Detectadas: decide si se prepara un borrador",
    nota: "«Preparar borrador» solo escribe el texto; publicarlo es un segundo paso.",
  },
  {
    status: "approved",
    titulo: "Preparándose",
    nota: "El servidor está escribiendo el borrador. Tarda un par de minutos por página.",
  },
  {
    status: "failed",
    titulo: "Atascadas",
    nota: "Nada se ha tocado en el sitio. El motivo va debajo de cada una.",
  },
];

export default async function AdminSeoOportunidadesPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/seo/oportunidades");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let items: Opportunity[] = [];
  let aplicadas: Opportunity[] = [];
  try {
    items = await apiFetch<Opportunity[]>("/admin/seo-opportunities?status=open");
  } catch {
    // silencioso: la página muestra estado vacío
  }
  try {
    // Lo último publicado, para poder revertirlo con la copia de antes.
    aplicadas = await apiFetch<Opportunity[]>(
      "/admin/seo-opportunities?status=applied&limit=15",
    );
  } catch {
    // idem
  }

  const periodo = items.find((i) => i.period)?.period ?? null;

  return (
    <AdminPage
      title="Oportunidades SEO"
      intro={
        <>
          Lo que Search Console dice que se está perdiendo, cruzado con lo que cada página cubre
          de verdad{periodo ? ` (datos de ${periodo})` : ""}. Cada una pasa por dos clics:{" "}
          <b className="text-ink">preparar</b> un borrador y, tras ver el antes/después,{" "}
          <b className="text-ink">publicarlo</b>.
        </>
      }
    >
      <Callout tone="info">
        Lo que la página ya responde y ya promete en Google no aparece aquí: ahí no falta
        contenido, falta posición.
      </Callout>

      {SECCIONES.map(({ status, titulo, nota }) => {
        const filas = items.filter((i) => i.status === status);
        return (
          <Section key={status} title={titulo} count={filas.length} help={nota}>
            {filas.length === 0 ? (
              <EmptyState>Nada por aquí.</EmptyState>
            ) : (
              <div className="space-y-3">
                {filas.map((it) => (
                  <OpportunityRow key={it.id} item={it} />
                ))}
              </div>
            )}
          </Section>
        );
      })}

      <Section
        title="Publicadas hace poco"
        count={aplicadas.length}
        help="Se guardó la página tal como estaba antes: «Revertir» la deja exactamente así, siempre que nadie la haya tocado después."
      >
        {aplicadas.length === 0 ? (
          <EmptyState>Nada por aquí.</EmptyState>
        ) : (
          <div className="space-y-3">
            {aplicadas.map((it) => (
              <OpportunityRow key={it.id} item={it} />
            ))}
          </div>
        )}
      </Section>
    </AdminPage>
  );
}
