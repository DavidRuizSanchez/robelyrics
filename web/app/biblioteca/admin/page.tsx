import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import { AdminPage, Callout, Card, StatusBadge, toneText } from "@/components/admin/ui";
import type { Tone } from "@/lib/admin/labels";

// Recuentos EXACTOS (COUNT en la BD, `app/services/admin_summary.py`): las
// pantallas de cada cola piden listas con límite y contarlas aquí mentiría.
type Summary = {
  ideas: { proposed: number; approved: number; scheduled: number };
  entradas: { pending_review: number; scheduled: number; bloqueadas: number };
  instagram: {
    proposed: number;
    pending: number;
    prepared: number;
    failed: number;
    needs_human: number;
    failed_sin_intentos: number;
  };
  clips: { requested: number; downloading: number; ready: number; failed: number };
  oportunidades: { detected: number; approved: number; drafted: number; failed: number };
  erratas: { pending: number; needs_human: number };
};

export const metadata = {
  title: "Admin · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

type Linea = { n: number; texto: string; tone: Tone };

function Panel({
  titulo,
  href,
  pendiente,
  lineas,
}: {
  titulo: string;
  href: string;
  /** Lo que pide una decisión tuya ahora. */
  pendiente: number;
  lineas: Linea[];
}) {
  const visibles = lineas.filter((l) => l.n > 0);
  return (
    <Card tone={pendiente > 0 ? "warn" : "ok"} className="flex flex-col">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-lg font-semibold text-ink">{titulo}</h2>
        {pendiente > 0 ? (
          <StatusBadge tone="warn">{pendiente} por decidir</StatusBadge>
        ) : (
          <StatusBadge tone="ok">✓ Al día</StatusBadge>
        )}
      </div>
      {visibles.length > 0 ? (
        <ul className="mt-3 space-y-1 text-sm">
          {visibles.map((l) => (
            <li key={l.texto} className="flex items-baseline gap-2">
              <span className={`font-mono w-10 text-right shrink-0 ${toneText(l.tone)}`}>
                {l.n}
              </span>
              <span className="text-ink-dim">{l.texto}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-ink-faint">Nada en marcha.</p>
      )}
      <Link href={href} className="mt-4 self-start text-sm text-accent hover:underline">
        Abrir {titulo} →
      </Link>
    </Card>
  );
}

export default async function AdminHomePage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let s: Summary | null = null;
  try {
    s = await apiFetch<Summary>("/admin/summary");
  } catch {
    s = null;
  }

  return (
    <AdminPage
      title="Panel"
      intro="Qué necesita tu atención hoy en cada parte de la web. Las cifras son recuentos exactos."
    >
      {!s ? (
        <Callout tone="danger" title="No se pudo cargar el resumen">
          Las secciones siguen funcionando desde el menú de arriba.
        </Callout>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <Panel
            titulo="Blog"
            href="/biblioteca/admin/blog"
            pendiente={s.entradas.pending_review + s.ideas.proposed}
            lineas={[
              { n: s.entradas.pending_review, texto: "entradas escritas esperan tu decisión", tone: "warn" },
              { n: s.entradas.bloqueadas, texto: "de ellas, frenadas por un control (hay que corregirlas)", tone: "danger" },
              { n: s.ideas.proposed, texto: "ideas por decidir", tone: "warn" },
              { n: s.ideas.approved, texto: "ideas aprobadas sin fecha", tone: "neutral" },
              { n: s.entradas.scheduled + s.ideas.scheduled, texto: "programadas", tone: "info" },
            ]}
          />
          <Panel
            titulo="Instagram"
            href="/biblioteca/admin/instagram"
            pendiente={s.instagram.proposed + s.instagram.needs_human + s.instagram.failed_sin_intentos}
            lineas={[
              { n: s.instagram.needs_human, texto: "posts necesitan que los mires", tone: "warn" },
              { n: s.instagram.proposed, texto: "propuestas por aprobar", tone: "warn" },
              { n: s.instagram.failed_sin_intentos, texto: "fallidos que ya no se reintentan", tone: "danger" },
              { n: s.instagram.failed - s.instagram.failed_sin_intentos, texto: "fallidos que se reintentarán solos", tone: "neutral" },
              { n: s.instagram.prepared, texto: "listos en la cola", tone: "ok" },
              { n: s.instagram.pending, texto: "en cola sin material todavía", tone: "neutral" },
              { n: s.clips.ready, texto: "clips listos para usar", tone: "ok" },
              { n: s.clips.requested + s.clips.downloading, texto: "clips bajándose", tone: "info" },
              { n: s.clips.failed, texto: "clips fallidos", tone: "danger" },
            ]}
          />
          <Panel
            titulo="Oportunidades SEO"
            href="/biblioteca/admin/seo/oportunidades"
            pendiente={s.oportunidades.drafted + s.oportunidades.detected}
            lineas={[
              { n: s.oportunidades.drafted, texto: "borradores listos para revisar y publicar", tone: "warn" },
              { n: s.oportunidades.detected, texto: "detectadas, sin borrador", tone: "warn" },
              { n: s.oportunidades.approved, texto: "preparándose", tone: "info" },
              { n: s.oportunidades.failed, texto: "atascadas", tone: "danger" },
            ]}
          />
          <Panel
            titulo="Erratas"
            href="/biblioteca/admin/erratas"
            pendiente={s.erratas.pending + s.erratas.needs_human}
            lineas={[
              { n: s.erratas.needs_human, texto: "necesitan tu criterio", tone: "warn" },
              { n: s.erratas.pending, texto: "sin revisar todavía", tone: "warn" },
            ]}
          />
        </div>
      )}
    </AdminPage>
  );
}
