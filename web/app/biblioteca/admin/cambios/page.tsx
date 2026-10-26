import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import { AdminPage, Callout, Metric, MetricGrid, Section, filterClass } from "@/components/admin/ui";
import { CAMBIO_CAMPO } from "@/lib/admin/labels";
import CambiosLista, { type CambioItem } from "./CambiosLista";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Cambios · Admin · Entre Interiores",
  robots: { index: false, follow: false },
};

type Respuesta = {
  total: number;
  por_campo: Record<string, number>;
  urls_vigiladas: number;
  ultima_pasada: {
    finished_at: string;
    urls: number;
    changed_urls: number;
    errors: number;
    baseline: boolean;
    global_event: boolean;
    notified: boolean;
  } | null;
  filas: CambioItem[];
};

const ESTADOS = [
  { value: "sin_ver", label: "Sin ver" },
  { value: "vistos", label: "Vistos" },
  { value: "todos", label: "Todos" },
];
const TIPOS = [
  { value: "todos", label: "Todos" },
  { value: "inesperados", label: "Sin causa conocida" },
  { value: "esperados", label: "Explicados por el sistema" },
];

function fecha(iso: string): string {
  return new Date(iso).toLocaleString("es-ES", {
    timeZone: "Europe/Madrid",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default async function AdminCambiosPage({
  searchParams,
}: {
  searchParams: Promise<{ estado?: string; tipo?: string; campo?: string }>;
}) {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/cambios");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  const sp = await searchParams;
  const estado = ESTADOS.some((e) => e.value === sp.estado) ? sp.estado! : "sin_ver";
  const tipo = TIPOS.some((t) => t.value === sp.tipo) ? sp.tipo! : "todos";
  const campo = sp.campo && CAMBIO_CAMPO[sp.campo] ? sp.campo : undefined;
  const qs = new URLSearchParams({ estado, tipo, ...(campo ? { campo } : {}) });

  let data: Respuesta = { total: 0, por_campo: {}, urls_vigiladas: 0, ultima_pasada: null, filas: [] };
  try {
    data = await apiFetch<Respuesta>(`/admin/cambios?${qs}`);
  } catch {
    // silencioso: la página muestra estado vacío
  }
  const url = (cambios: Record<string, string | undefined>) => {
    const p = new URLSearchParams({ estado, tipo, ...(campo ? { campo } : {}) });
    for (const [k, v] of Object.entries(cambios)) {
      if (v === undefined) p.delete(k);
      else p.set(k, v);
    }
    return `/biblioteca/admin/cambios?${p}`;
  };
  const ult = data.ultima_pasada;

  return (
    <AdminPage
      title="Cambios en la web"
      intro="Cada mañana el sistema fotografía todas las páginas del sitemap y las compara con la foto del día anterior: title, description, encabezados, contenido, robots, canonical, código HTTP y redirecciones. Lo que no explica nada que haya hecho el propio sistema va primero."
    >
      <Callout tone="info" title="Modo sombra">
        Esta primera semana los cambios se guardan y se ven aquí, pero no llega correo: sirve para medir
        cuánto ruido hay antes de avisar. El correo se enciende con <code>MONITOR_CAMBIOS_CORREO=1</code>.
      </Callout>

      <MetricGrid>
        <Metric label="Páginas vigiladas" value={data.urls_vigiladas} />
        <Metric
          label="Última pasada"
          value={ult ? fecha(ult.finished_at) : "Todavía ninguna"}
          hint={
            ult
              ? ult.baseline
                ? "Fue la foto de referencia: a partir de la siguiente se compara."
                : `${ult.changed_urls} de ${ult.urls} páginas con cambios${ult.errors ? ` · ${ult.errors} sin responder` : ""}`
              : undefined
          }
        />
        <Metric label="Cambios en esta vista" value={data.total} />
      </MetricGrid>

      {ult?.global_event && (
        <Callout tone="warn" title="Cambió mucho de golpe">
          En la última pasada cambió más de un 30 % de la web. Suele ser la plantilla (un deploy) o una caída:
          mira primero si es lo mismo en todas.
        </Callout>
      )}

      <Section title="Filtros">
        <div className="flex flex-wrap gap-2">
          {ESTADOS.map((e) => (
            <Link key={e.value} href={url({ estado: e.value })} className={filterClass(estado === e.value)}>
              {e.label}
            </Link>
          ))}
          <span className="mx-2 border-l border-divider" aria-hidden />
          {TIPOS.map((t) => (
            <Link key={t.value} href={url({ tipo: t.value })} className={filterClass(tipo === t.value)}>
              {t.label}
            </Link>
          ))}
        </div>
        {Object.keys(data.por_campo).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href={url({ campo: undefined })} className={filterClass(!campo)}>
              Cualquier campo
            </Link>
            {Object.entries(data.por_campo)
              .sort((a, b) => b[1] - a[1])
              .map(([k, n]) => (
                <Link key={k} href={url({ campo: k })} className={filterClass(campo === k)}>
                  {CAMBIO_CAMPO[k] ?? k} <span className="font-mono text-xs text-ink-faint">{n}</span>
                </Link>
              ))}
          </div>
        )}
      </Section>

      <Section
        title="Cambios"
        count={data.total > data.filas.length ? `${data.total} (se ven ${data.filas.length})` : data.total}
        help="Primero lo que no tiene causa conocida y, dentro, lo más grave. «Marcar como visto» solo lo quita de esta lista: no deshace nada."
      >
        <CambiosLista
          items={data.filas}
          vacio={
            ult
              ? "Nada que revisar con estos filtros."
              : "El monitor todavía no ha pasado: la primera pasada es la foto de referencia."
          }
        />
      </Section>
    </AdminPage>
  );
}
