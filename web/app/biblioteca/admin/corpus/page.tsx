import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import { AdminPage, Callout, EmptyState, Section } from "@/components/admin/ui";
import CorpusRow, { type CorpusItem } from "./CorpusRow";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Corpus · Admin · Entre Interiores",
  robots: { index: false, follow: false },
};

type Cola = {
  cuenta: Record<string, number>;
  filas: Record<string, CorpusItem[]>;
};

function Lista({ items, vacio }: { items: CorpusItem[]; vacio: string }) {
  if (items.length === 0) return <EmptyState>{vacio}</EmptyState>;
  return (
    <div className="space-y-3">
      {items.map((it) => (
        <CorpusRow key={it.id} item={it} />
      ))}
    </div>
  );
}

// Si la sección enseña menos filas de las que hay, se dice: el recuento es un
// COUNT en la BD y la lista tiene tope.
function cuantos(total: number, enseñados: number): string {
  return total > enseñados ? `${total} (se ven ${enseñados})` : String(total);
}

export default async function AdminCorpusPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/corpus");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let cola: Cola = { cuenta: {}, filas: {} };
  try {
    cola = await apiFetch<Cola>("/admin/corpus/queue");
  } catch {
    // silencioso: la página muestra estado vacío
  }
  const f = (estado: string) => cola.filas[estado] ?? [];
  const n = (estado: string) => cola.cuenta[estado] ?? 0;

  return (
    <AdminPage
      title="Corpus"
      intro="Vídeos de YouTube que pueden entrar en el corpus. El sistema los busca, los clasifica por lo que se fía de ellos, y tú decides. Al aprobar uno, tu Mac lo transcribe y lo sube."
    >
      <Callout tone="info" title="Modo sombra">
        Por ahora nada entra solo: también lo que el sistema da por bueno (niveles A y B) espera tu
        clic. Cuando lleves dos semanas sin rechazar ningún A, se puede activar la entrada automática.
      </Callout>

      <Section
        title="Por decidir"
        count={cuantos(n("detected"), f("detected").length)}
        help="Primero lo que más se fía el sistema (A, luego B, luego C). Abre el vídeo si dudas: el enlace va a YouTube."
      >
        <Lista items={f("detected")} vacio="Nada pendiente." />
      </Section>

      <Section
        title="Fallidos"
        count={cuantos(n("failed"), f("failed").length)}
        help="Tu Mac no pudo bajarlo o transcribirlo. Se reintentan solos hasta tres veces; aquí puedes forzarlo o descartarlo."
      >
        <Lista items={f("failed")} vacio="Ninguno." />
      </Section>

      <Section title="En marcha" count={n("approved") + n("processing")}>
        <Lista items={[...f("processing"), ...f("approved")]} vacio="Nada esperando a tu Mac." />
      </Section>

      <Section title="Últimos que entraron" count={n("done")}>
        <Lista items={f("done")} vacio="Todavía nada." />
      </Section>

      <Section title="Descartados" count={n("retired")} help="No vuelven a proponerse.">
        <Lista items={f("retired")} vacio="Ninguno." />
      </Section>
    </AdminPage>
  );
}
