import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import OpportunityRow, { type Opportunity } from "./OpportunityRow";

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
    titulo: "borradores listos · esperan tu visto bueno",
    nota: "Esto es lo que se publicaría, tal cual. Nada está en el sitio todavía.",
  },
  {
    status: "detected",
    titulo: "detectadas · esperan que autorices el borrador",
    nota: "Aprobar aquí solo PREPARA el texto; publicar es un segundo paso.",
  },
  {
    status: "approved",
    titulo: "preparándose",
    nota: "El servidor está escribiendo el borrador. Tarda un par de minutos por página.",
  },
  {
    status: "failed",
    titulo: "se atascaron",
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
  try {
    items = await apiFetch<Opportunity[]>("/admin/seo-opportunities?status=open");
  } catch {
    // silencioso: la página muestra estado vacío
  }

  const periodo = items.find((i) => i.period)?.period ?? null;

  return (
    <div className="max-w-[860px] space-y-12">
      <header>
        <h1 className="font-mono text-[11px] tracking-[3px] uppercase text-accent mb-1">
          Oportunidades SEO
        </h1>
        <p className="font-serif italic text-ink-dim text-sm">
          Lo que Search Console dice que se está perdiendo, cruzado con lo que la página
          cubre de verdad{periodo ? ` · datos de ${periodo}` : ""}.
        </p>
        <p className="font-serif italic text-ink-faint text-[13px] mt-2">
          Lo que ya está respondido en el cuerpo y prometido en la metadata no aparece aquí:
          ahí no falta contenido, falta posición.
        </p>
      </header>

      {SECCIONES.map(({ status, titulo, nota }) => {
        const filas = items.filter((i) => i.status === status);
        return (
          <section key={status}>
            <h2 className="font-mono text-[11px] tracking-[3px] uppercase text-accent mb-1">
              {titulo} ({filas.length})
            </h2>
            <p className="font-serif italic text-ink-dim text-sm mb-4">{nota}</p>
            {filas.length === 0 ? (
              <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
                Nada por aquí.
              </p>
            ) : (
              <div>
                {filas.map((it) => (
                  <OpportunityRow key={it.id} item={it} />
                ))}
              </div>
            )}
          </section>
        );
      })}

      <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
        <Link href="/biblioteca/admin/seo" className="hover:text-accent">
          ← fichas SEO
        </Link>
      </p>
    </div>
  );
}
