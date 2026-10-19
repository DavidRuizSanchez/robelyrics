"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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
    protegidas?: number;
    before_len?: number;
    after_len?: number;
  } | null;
  error: string | null;
  attempts: number;
  proposal_id?: number | null;
  revertible?: boolean;
};

const ACCION_LABEL: Record<string, string> = {
  meta: "falta promesa · title y description",
  body: "falta contenido · se amplía sin tocar lo que ya dice",
  merge: "fusión con una propuesta del blog · se amplía y se revisa la página entera",
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
  return (
    <div className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-3">
      {children}
    </div>
  );
}

/** El antes/después de una fusión: un mapa de la página, no una cola añadida. */
function DiffFusion({ o }: { o: Opportunity }) {
  const n = o.draft_notes || {};
  const nuevas = new Set((n.added_headings || []).map((h) => h.toLowerCase()));
  const renombres = new Map((n.renamed || []).map((r) => [r.new.toLowerCase(), r]));
  const bloques = trocear(o.draft_body || "");
  return (
    <>
      <Mini>estructura resultante</Mini>
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
              <li key={i} className="text-accent">
                + {b.heading}
              </li>
            );
          const r = renombres.get(h);
          if (r)
            return (
              <li key={i} className="text-ink">
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
      <div className="font-mono text-[10px] text-ink-faint">
        {n.before_len} → {n.after_len} caracteres
        {n.rigor ? ` · rigor ${n.rigor.before_score} → ${n.rigor.score} (${n.rigor.verdict})` : ""}
        {` · ${n.protegidas ?? 0} búsquedas protegidas siguen cubiertas`}
      </div>
      {n.intro_rewritten && (
        <>
          <Mini>intro</Mini>
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
          <Mini>heading renombrado</Mini>
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
            <Mini>sección nueva</Mini>
            <pre className="font-serif text-sm text-ink/85 whitespace-pre-wrap">{b.texto}</pre>
          </div>
        ))}
      {(n.puentes || []).map((p) => (
        <div key={p.after + p.texto}>
          <Mini>frase puente tras «{p.after}»</Mini>
          <p className="font-serif text-sm text-ink/85">{p.texto}</p>
        </div>
      ))}
      {(o.draft_title || o.draft_description) && (
        <>
          <Mini>title y description</Mini>
          {o.draft_title && (
            <p className="font-serif text-sm">
              <span className="line-through text-ink-dim">{o.before_title || "(vacío)"}</span>
              <br />
              {o.draft_title}
            </p>
          )}
          {o.draft_description && (
            <p className="font-serif text-sm mt-1">
              <span className="line-through text-ink-dim">
                {o.before_description || "(vacío)"}
              </span>
              <br />
              {o.draft_description}
            </p>
          )}
        </>
      )}
      {(n.descartado?.length ?? 0) > 0 && (
        <>
          <Mini>lo que las guardas descartaron</Mini>
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

  if (hecho) {
    return (
      <div className="border-b border-ink/[0.06] py-4">
        <span className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
          {item.path} · {hecho}
        </span>
      </div>
    );
  }

  return (
    <div
      className={
        forzada
          ? "border-b border-ink/[0.06] py-5 pl-3 border-l-2 border-l-accent/60"
          : "border-b border-ink/[0.06] py-5"
      }
    >
      <div className="flex flex-wrap items-baseline gap-x-3">
        <a
          href={item.path}
          target="_blank"
          rel="noreferrer"
          className="font-serif text-[17px] text-ink hover:text-accent"
        >
          {item.path}
        </a>
        <span className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
          {item.impressions} imp
        </span>
      </div>
      <p className="font-serif italic text-sm text-ink-dim mt-1">{ACCION_LABEL[item.action]}</p>

      {item.queries && item.queries.length > 0 && (
        <ul className="mt-2 space-y-1">
          {item.queries.slice(0, 4).map((q) => (
            <li key={q.query} className="font-serif text-sm text-ink/80">
              «{q.query}»{" "}
              <span className="font-mono text-[10px] text-ink-faint">
                {q.position !== null && q.position !== undefined
                  ? `pos ${q.position.toFixed(1)} · ${q.impressions} imp · ${q.clicks ?? 0} clic`
                  : `sin datos GSC en esta página${q.volume ? ` · ${q.volume} búsquedas/mes` : ""}`}
              </span>
            </li>
          ))}
        </ul>
      )}

      {item.status === "drafted" && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setAbierto((v) => !v)}
            className="font-mono text-[10px] tracking-[2px] uppercase text-accent"
          >
            {abierto ? "ocultar el antes/después" : "ver el antes/después"}
          </button>
          {abierto && (
            <div className="mt-3 border border-ink/[0.08] bg-ink/[0.02] p-4 space-y-3">
              {item.action === "merge" ? (
                <DiffFusion o={item} />
              ) : item.action === "meta" ? (
                <>
                  {item.draft_title && (
                    <div>
                      <div className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                        title
                      </div>
                      <div className="font-serif text-sm text-ink-dim line-through">
                        {item.before_title || "(vacío)"}
                      </div>
                      <div className="font-serif text-[15px] text-ink">{item.draft_title}</div>
                    </div>
                  )}
                  {item.draft_description && (
                    <div>
                      <div className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                        description
                      </div>
                      <div className="font-serif text-sm text-ink-dim line-through">
                        {item.before_description || "(vacío)"}
                      </div>
                      <div className="font-serif text-[15px] text-ink">
                        {item.draft_description}{" "}
                        <span className="font-mono text-[10px] text-ink-faint">
                          {item.draft_description.length}c
                        </span>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                    secciones nuevas: {(item.draft_notes?.added_headings || []).join(", ") || "—"}
                  </div>
                  <pre className="font-serif text-sm text-ink/85 whitespace-pre-wrap">
                    {textoAnadido(item)}
                  </pre>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Los avisos no bloquean, pero son lo que hay que mirar antes de publicar:
          «es un resumen, no una promesa» es la crítica que originó este criterio. */}
      {(item.draft_notes?.avisos?.length ?? 0) > 0 && (
        <ul className="mt-2 border-l-2 border-accent/40 pl-3 space-y-0.5">
          {item.draft_notes!.avisos!.map((a) => (
            <li key={a} className="font-serif text-[13px] text-ink-dim">
              {a}
            </li>
          ))}
        </ul>
      )}
      {item.error && (
        <p className="font-mono text-[10px] text-accent mt-2">{item.error}</p>
      )}
      {error && <p className="font-mono text-[10px] text-accent mt-2">{error}</p>}

      <div className="mt-3 flex gap-4">
        {item.status === "detected" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => mover("approve")}
            className="font-mono text-[10px] tracking-[2px] uppercase text-accent disabled:opacity-40"
          >
            preparar borrador
          </button>
        )}
        {item.status === "drafted" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => mover("apply")}
            className="font-mono text-[10px] tracking-[2px] uppercase text-accent disabled:opacity-40"
          >
            {forzada ? "publicar igualmente" : "publicar"}
          </button>
        )}
        {item.status === "failed" && (
          <button
            type="button"
            disabled={busy || item.attempts >= 3}
            onClick={() => mover("approve")}
            className="font-mono text-[10px] tracking-[2px] uppercase text-accent disabled:opacity-40"
          >
            reintentar
          </button>
        )}
        {item.status === "applied" && item.revertible && (
          <button
            type="button"
            disabled={busy}
            onClick={() => mover("revert")}
            className="font-mono text-[10px] tracking-[2px] uppercase text-accent disabled:opacity-40"
          >
            revertir
          </button>
        )}
        {item.status !== "applied" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => mover("discard")}
            className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint disabled:opacity-40"
          >
            descartar
          </button>
        )}
      </div>
    </div>
  );
}
