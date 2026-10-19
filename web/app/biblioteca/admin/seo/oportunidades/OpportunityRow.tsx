"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Term from "@/components/admin/Term";
import {
  ActionBar,
  Button,
  Callout,
  Card,
  Eyebrow,
  JobStatus,
  Notice,
  StatusBadge,
  Table,
  cx,
  tdClass,
} from "@/components/admin/ui";
import { OPPORTUNITY_ACTION, OPPORTUNITY_STATUS, etiqueta } from "@/lib/admin/labels";

export type GscQuery = {
  query: string;
  impressions: number;
  clicks?: number;
  // En una fusión la consulta puede no tener dato GSC en esa página todavía
  // (viene de la propuesta, con su volumen de búsqueda).
  position: number | null;
  volume?: number;
};

export type Opportunity = {
  id: number;
  path: string;
  action: string;
  status: string;
  impressions: number;
  period: string | null;
  gap_hint: string | null;
  queries: GscQuery[] | null;
  before_title: string | null;
  before_description: string | null;
  before_body: string | null;
  draft_title: string | null;
  draft_description: string | null;
  draft_body: string | null;
  draft_notes: {
    added_headings?: string[];
    rigor?: {
      verdict?: string;
      score?: number;
      before_score?: number;
      reasons?: string[];
      forzada?: boolean;
    };
    rechazos?: string[];
    avisos?: string[];
    // Solo en `merge` (ver scripts/seo/merge_deep.py).
    renamed?: { old: string; new: string; why?: string }[];
    intro_rewritten?: boolean;
    intro_before?: string | null;
    puentes?: { after: string; texto: string }[];
    images_added?: { url: string; alt: string; section: string; status: string }[];
    videos_added?: { url: string; section: string }[] | string[];
    descartado?: string[];
    enriched?: { heading: string; texto: string }[];
    juez?: { op: string; vuelta: number; antes: number; despues: number; veredicto: string }[];
    corroboracion?: { verificados: string[]; descartados: string[] };
    protegidas?: number;
    before_len?: number;
    after_len?: number;
  } | null;
  error: string | null;
  attempts: number;
  proposal_id?: number | null;
  revertible?: boolean;
};

type Bloque = { heading: string | null; texto: string };

/** Mismo troceo por H2 que `merge_deep.trocear`, para pintar el mapa. */
function trocear(body: string): Bloque[] {
  const lineas = (body || "").split("\n");
  const out: Bloque[] = [];
  let actual: Bloque = { heading: null, texto: "" };
  for (const l of lineas) {
    const m = l.match(/^##(?!#)\s*(.+?)\s*$/);
    if (m) {
      if (actual.texto.trim()) out.push(actual);
      actual = { heading: m[1], texto: l };
    } else {
      actual.texto += (actual.texto ? "\n" : "") + l;
    }
  }
  if (actual.texto.trim()) out.push(actual);
  return out;
}

function Mini({ children }: { children: React.ReactNode }) {
  return <Eyebrow className="mt-4 mb-1">{children}</Eyebrow>;
}

/** Antes tachado y después en claro: el formato de todos los cambios de texto. */
function AntesDespues({ antes, despues, nota }: { antes: string | null; despues: string; nota?: string }) {
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <div className="rounded border border-divider p-2">
        <p className="text-xs text-ink-faint mb-0.5">Antes</p>
        <p className="font-serif text-sm text-ink-dim line-through decoration-ink-faint">{antes || "(vacío)"}</p>
      </div>
      <div className="rounded border border-ok/30 bg-ok-bg p-2">
        <p className="text-xs text-ok mb-0.5">Después{nota ? ` · ${nota}` : ""}</p>
        <p className="font-serif text-[15px] text-ink">{despues}</p>
      </div>
    </div>
  );
}

const PASOS: { key: string; label: string }[] = [
  { key: "detected", label: "Detectada" },
  { key: "drafted", label: "Borrador listo" },
  { key: "applied", label: "Publicada" },
];

/** Dónde está en el circuito de dos clics: preparar → publicar. */
function Pasos({ status }: { status: string }) {
  const idx =
    status === "applied" ? 2 : status === "drafted" ? 1 : status === "approved" ? 0.5 : 0;
  return (
    <ol className="flex flex-wrap items-center gap-1 text-xs" aria-label="Progreso">
      {PASOS.map((p, i) => {
        const hecho = i < idx || (i === 2 && idx === 2);
        const actual = i === Math.ceil(idx) && !(i === 2 && idx === 2);
        return (
          <li key={p.key} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden className="text-ink-faint">→</span>}
            <span
              className={cx(
                "rounded-full px-2 py-0.5 border",
                hecho
                  ? "border-ok/30 text-ok"
                  : actual
                    ? "border-warn/40 text-warn"
                    : "border-divider text-ink-faint",
              )}
              aria-current={actual ? "step" : undefined}
            >
              {hecho ? "✓ " : ""}
              {p.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** El antes/después de una fusión: un mapa de la página, no una cola añadida. */
function DiffFusion({ o }: { o: Opportunity }) {
  const n = o.draft_notes || {};
  const nuevas = new Set((n.added_headings || []).map((h) => h.toLowerCase()));
  const renombres = new Map((n.renamed || []).map((r) => [r.new.toLowerCase(), r]));
  const enriquecidas = new Map((n.enriched || []).map((e) => [e.heading.toLowerCase(), e]));
  const juez = new Map((n.juez || []).map((j) => [j.op, j]));
  const bloques = trocear(o.draft_body || "");
  return (
    <>
      <Mini>Cómo queda la página</Mini>
      <p className="text-xs text-ink-faint mb-1">
        <span className="text-ok">+ nueva</span> · <span className="text-info">± ampliada</span> ·{" "}
        <span className="text-warn">~ renombrada</span> · el resto queda igual
      </p>
      <ol className="font-serif text-sm space-y-0.5">
        {bloques.map((b, i) => {
          if (b.heading === null)
            return (
              <li key={i} className="text-ink-dim">
                (intro){n.intro_rewritten ? " · reescrita" : ""}
              </li>
            );
          const h = b.heading.toLowerCase();
          if (nuevas.has(h))
            return (
              <li key={i} className="text-ok">
                + {b.heading}
              </li>
            );
          if (enriquecidas.has(h))
            return (
              <li key={i} className="text-info">
                ± {b.heading} <span className="text-ink-faint">(se le añade un párrafo)</span>
              </li>
            );
          const r = renombres.get(h);
          if (r)
            return (
              <li key={i} className="text-warn">
                ~ {b.heading}{" "}
                <span className="text-ink-faint">(antes «{r.old}»)</span>
              </li>
            );
          return (
            <li key={i} className="text-ink-faint">
              {b.heading}
            </li>
          );
        })}
      </ol>
      <div className="mt-2 text-xs text-ink-faint">
        Longitud {n.before_len} → {n.after_len} caracteres
        {n.rigor ? ` · rigor ${n.rigor.before_score} → ${n.rigor.score} (${n.rigor.verdict})` : ""}
        {` · ${n.protegidas ?? 0} búsquedas protegidas siguen cubiertas`}
      </div>
      {n.intro_rewritten && (
        <>
          <Mini>Introducción</Mini>
          <p className="font-serif text-sm text-ink-dim line-through whitespace-pre-wrap">
            {n.intro_before}
          </p>
          <p className="font-serif text-sm text-ink whitespace-pre-wrap">
            {bloques[0]?.heading === null ? bloques[0].texto : ""}
          </p>
        </>
      )}
      {(n.renamed || []).map((r) => (
        <div key={r.old}>
          <Mini>Título de sección cambiado</Mini>
          <p className="font-serif text-sm">
            <span className="line-through text-ink-dim">{r.old}</span> → {r.new}
          </p>
          {r.why && <p className="font-serif italic text-[13px] text-ink-faint">{r.why}</p>}
        </div>
      ))}
      {bloques
        .filter((b) => b.heading && nuevas.has(b.heading.toLowerCase()))
        .map((b) => (
          <div key={b.heading}>
            <Mini>Sección nueva</Mini>
            <pre className="font-serif text-sm text-ink/85 whitespace-pre-wrap">{b.texto}</pre>
          </div>
        ))}
      {(n.enriched || []).map((e) => (
        <div key={e.heading}>
          <Mini>Se añade al final de «{e.heading}»</Mini>
          <p className="font-serif text-sm text-ink/85 whitespace-pre-wrap">{e.texto}</p>
        </div>
      ))}
      {juez.size > 0 && (
        <>
          <Mini>Nota del editor jefe en cada cambio (antes → después)</Mini>
          <ul className="font-serif text-[13px] text-ink-dim list-disc pl-5">
            {[...juez.values()].map((j) => (
              <li key={j.op}>
                «{j.op}»: {j.antes} → {j.despues} ({j.veredicto}
                {j.vuelta ? `, tras ${j.vuelta} reescritura${j.vuelta > 1 ? "s" : ""}` : ""})
              </li>
            ))}
          </ul>
        </>
      )}
      {(n.corroboracion?.descartados?.length ?? 0) > 0 && (
        <>
          <Mini>Datos de terceros que NO se han escrito (sin corroborar)</Mini>
          <ul className="font-serif text-[13px] text-ink-faint list-disc pl-5">
            {n.corroboracion!.descartados.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </>
      )}
      {(n.puentes || []).map((p) => (
        <div key={p.after + p.texto}>
          <Mini>Frase de enlace tras «{p.after}»</Mini>
          <p className="font-serif text-sm text-ink/85">{p.texto}</p>
        </div>
      ))}
      {(o.draft_title || o.draft_description) && (
        <>
          <Mini>Lo que se ve en Google</Mini>
          <div className="space-y-2">
            {o.draft_title && <AntesDespues antes={o.before_title} despues={o.draft_title} nota="título" />}
            {o.draft_description && (
              <AntesDespues antes={o.before_description} despues={o.draft_description} nota="descripción" />
            )}
          </div>
        </>
      )}
      {(n.descartado?.length ?? 0) > 0 && (
        <>
          <Mini>Lo que los controles descartaron</Mini>
          <ul className="font-serif text-[13px] text-ink-faint list-disc pl-5">
            {n.descartado!.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

/** Lo que la ampliación añade: `augment_entity` escribe al final sin reescribir. */
function textoAnadido(o: Opportunity): string {
  const antes = o.before_body ?? "";
  const despues = o.draft_body ?? "";
  if (despues.startsWith(antes.slice(0, Math.max(0, antes.length - 200)))) {
    return despues.slice(antes.length).trim();
  }
  return despues.slice(-2500);
}

export default function OpportunityRow({ item }: { item: Opportunity }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  // Lo que el editor jefe rechaza se abre solo: un texto que sale con el veredicto
  // en contra no se puede publicar a ciegas, y un clic de más para verlo es un clic
  // que nadie da.
  const forzada = item.draft_notes?.rigor?.forzada === true;
  const [abierto, setAbierto] = useState(forzada);
  const [error, setError] = useState<string | null>(null);
  const [hecho, setHecho] = useState<string | null>(null);

  async function mover(accion: "approve" | "apply" | "discard" | "revert") {
    if (
      accion === "revert" &&
      !window.confirm(
        "¿Revertir? La página vuelve EXACTAMENTE a como estaba antes de aplicar.",
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/biblioteca/admin/seo/oportunidades/api/${item.id}/${accion}`,
        { method: "POST" },
      );
      const data = (await res.json()) as { error?: string };
      if (!res.ok) throw new Error(data?.error || "");
      setHecho(
        accion === "approve"
          ? "preparando el borrador…"
          : accion === "apply"
            ? "publicado"
            : accion === "revert"
              ? "revertida"
              : "descartada",
      );
      router.refresh();
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "No se pudo completar.");
      setBusy(false);
    }
  }

  const st = etiqueta(OPPORTUNITY_STATUS, item.status);
  const acc = etiqueta(OPPORTUNITY_ACTION, item.action);
  const bloqueada = item.status === "failed" && item.attempts >= 3;

  if (hecho) {
    return (
      <Card tone="ok">
        <p className="text-sm text-ink-dim">
          <span className="font-mono text-ink">{item.path}</span> · {hecho}
        </p>
      </Card>
    );
  }

  return (
    <Card tone={forzada ? "danger" : st.tone}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <a
            href={item.path}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-[15px] text-ink hover:text-accent break-all"
          >
            {item.path} ↗
          </a>
          <p className="mt-1 text-ink">
            {acc.label}
            <span className="text-ink-dim"> — {acc.hint}</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge tone={st.tone} title={st.hint}>
            {st.label}
          </StatusBadge>
          <StatusBadge>
            {item.impressions.toLocaleString("es-ES")} <Term k="impresiones">impresiones</Term>
          </StatusBadge>
        </div>
      </div>

      <div className="mt-3">
        <Pasos status={item.status} />
      </div>

      {item.status === "approved" && (
        <div className="mt-3">
          <JobStatus label="Escribiendo el borrador" hint="tarda un par de minutos por página" />
        </div>
      )}

      {item.queries && item.queries.length > 0 && (
        <div className="mt-4">
          <Eyebrow className="mb-1">Lo que busca la gente</Eyebrow>
          <Table
            head={[
              "Búsqueda",
              <Term key="p" k="posicion">Posición</Term>,
              <Term key="i" k="impresiones">Impresiones</Term>,
              "Clics",
            ]}
          >
            {item.queries.slice(0, 4).map((q) => (
              <tr key={q.query}>
                <td className={cx(tdClass, "font-mono text-[13px] text-ink")}>{q.query}</td>
                {q.position !== null && q.position !== undefined ? (
                  <>
                    <td className={cx(tdClass, "font-mono")}>
                      {q.position.toLocaleString("es-ES", { maximumFractionDigits: 1 })}
                    </td>
                    <td className={cx(tdClass, "font-mono")}>{q.impressions.toLocaleString("es-ES")}</td>
                    <td className={cx(tdClass, "font-mono")}>{(q.clicks ?? 0).toLocaleString("es-ES")}</td>
                  </>
                ) : (
                  <td className={cx(tdClass, "text-ink-faint")} colSpan={3}>
                    Sin datos de Search Console en esta página
                    {q.volume ? ` · ${q.volume.toLocaleString("es-ES")} búsquedas/mes` : ""}
                  </td>
                )}
              </tr>
            ))}
          </Table>
          {item.queries.length > 4 && (
            <p className="mt-1 text-xs text-ink-faint">y {item.queries.length - 4} búsquedas más</p>
          )}
        </div>
      )}

      {forzada && (
        <Callout tone="danger" className="mt-4" title="El editor jefe rechazó este borrador">
          Puede publicarse igualmente, pero revisa el antes/después primero.
        </Callout>
      )}

      {/* Los avisos no bloquean, pero son lo que hay que mirar antes de publicar:
          «es un resumen, no una promesa» es la crítica que originó este criterio. */}
      {(item.draft_notes?.avisos?.length ?? 0) > 0 && (
        <Callout tone="warn" className="mt-3" title="Míralo antes de publicar">
          <ul className="list-disc pl-5 space-y-0.5">
            {item.draft_notes!.avisos!.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Callout>
      )}

      {item.status === "drafted" && (
        <div className="mt-4">
          {/* Lo que el editor jefe rechaza se abre solo (ver `abierto`). */}
          <details open={abierto} onToggle={(e) => setAbierto((e.target as HTMLDetailsElement).open)} className="group/det">
            <summary className="cursor-pointer list-none inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline [&::-webkit-details-marker]:hidden">
              <span aria-hidden className="text-[10px] transition-transform group-open/det:rotate-90">▶</span>
              Ver el antes/después
            </summary>
            <div className="mt-3 rounded-md border border-divider bg-bg/60 p-4 space-y-3">
              {item.action === "merge" ? (
                <DiffFusion o={item} />
              ) : item.action === "meta" ? (
                <div className="space-y-2">
                  {item.draft_title && (
                    <AntesDespues antes={item.before_title} despues={item.draft_title} nota="título" />
                  )}
                  {item.draft_description && (
                    <AntesDespues
                      antes={item.before_description}
                      despues={item.draft_description}
                      nota={`descripción · ${item.draft_description.length} caracteres`}
                    />
                  )}
                </div>
              ) : (
                <>
                  <p className="text-sm text-ink-dim">
                    Secciones nuevas:{" "}
                    <span className="text-ok">
                      {(item.draft_notes?.added_headings || []).join(", ") || "—"}
                    </span>
                  </p>
                  <Mini>Texto que se añade al final</Mini>
                  <pre className="font-serif text-sm text-ink/85 whitespace-pre-wrap">{textoAnadido(item)}</pre>
                </>
              )}
            </div>
          </details>
        </div>
      )}

      {item.error && (
        <Callout tone="danger" className="mt-3" title={bloqueada ? "Falló 3 veces: ya no se reintenta" : "Último intento fallido"}>
          <span className="font-mono text-xs break-words">{item.error}</span>
        </Callout>
      )}
      {error && (
        <div className="mt-3">
          <Notice onClose={() => setError(null)}>{error}</Notice>
        </div>
      )}

      <ActionBar
        primary={
          <>
            {item.status === "detected" && (
              <Button
                variant="primary"
                loading={busy}
                onClick={() => mover("approve")}
                title="Solo prepara el texto: publicar es un segundo paso"
              >
                Preparar borrador
              </Button>
            )}
            {item.status === "drafted" && (
              <Button variant={forzada ? "secondary" : "primary"} loading={busy} onClick={() => mover("apply")}>
                {forzada ? "Publicar igualmente" : "Publicar en la web"}
              </Button>
            )}
            {item.status === "failed" && (
              <Button disabled={busy || bloqueada} onClick={() => mover("approve")}>
                Reintentar
              </Button>
            )}
          </>
        }
        danger={
          <>
            {item.status === "applied" && item.revertible && (
              <Button variant="danger" disabled={busy} onClick={() => mover("revert")}>
                Revertir
              </Button>
            )}
            {item.status !== "applied" && (
              <Button variant="danger" disabled={busy} onClick={() => mover("discard")}>
                Descartar
              </Button>
            )}
          </>
        }
      />
    </Card>
  );
}
