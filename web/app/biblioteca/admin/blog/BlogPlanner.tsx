"use client";

import Link from "next/link";
import { useState } from "react";
import type { ProposalItem } from "./page";

const KIND_LABEL: Record<string, string> = {
  news: "Noticia",
  anniversary: "Efeméride Robe",
  "album-anniversary": "Aniversario disco",
  spotlight: "Análisis canción",
  evergreen: "Tema de fondo",
};

// Grupos para el filtro por tipo.
const FILTERS: { key: string; label: string; kinds: Set<string> | null }[] = [
  { key: "all", label: "todo", kinds: null },
  { key: "actualidad", label: "actualidad", kinds: new Set(["news"]) },
  {
    key: "efemerides",
    label: "efemérides",
    kinds: new Set(["anniversary", "album-anniversary"]),
  },
  { key: "spotlight", label: "spotlight", kinds: new Set(["spotlight"]) },
  { key: "evergreen", label: "evergreen", kinds: new Set(["evergreen"]) },
];

// Formatea en UTC para que SSR (server, UTC) y cliente coincidan: evita el
// desajuste de hidratación y el corrimiento de día por zona horaria.
function fmtDate(iso: string): string {
  return new Date(iso + "T00:00:00Z").toLocaleDateString("es-ES", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

// Lunes de la semana natural de una fecha ISO (YYYY-MM-DD), operando en UTC.
function mondayOf(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  const day = (d.getUTCDay() + 6) % 7; // 0 = lunes
  d.setUTCDate(d.getUTCDate() - day);
  return d.toISOString().slice(0, 10);
}

export default function BlogPlanner({
  proposed,
  approved,
  scheduled,
  discarded,
}: {
  proposed: ProposalItem[];
  approved: ProposalItem[];
  scheduled: ProposalItem[];
  discarded: ProposalItem[];
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [dates, setDates] = useState<Record<number, string>>({});
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState<string>("all");
  const [weeks, setWeeks] = useState<number>(4);

  function matchesFilter(p: ProposalItem): boolean {
    const f = FILTERS.find((x) => x.key === filter);
    return !f || f.kinds === null || f.kinds.has(p.kind);
  }

  function toggleSelected(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function post(path: string, body?: Record<string, unknown>) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `Error ${res.status}`);
    }
    return res;
  }

  async function call(action: string, id: number, body?: Record<string, unknown>) {
    setBusy(id);
    try {
      await post(`/biblioteca/admin/blog/api/${action}/${id}`, body);
      window.location.reload();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function bulkApprove(ids: number[]) {
    if (ids.length === 0) return;
    if (
      !window.confirm(
        `¿Aprobar ${ids.length} propuesta(s)? Las noticias quedan listas al ` +
          `momento; el resto generan su borrador en unos minutos (automático).`,
      )
    )
      return;
    setBusy(-1);
    try {
      // Una sola petición: marca todo aprobado al instante. Los borradores
      // (evergreen/spotlight/efeméride) los genera el cron cada pocos minutos.
      await post("/biblioteca/admin/blog/api/bulk-approve", { ids });
      window.location.reload();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function autoSchedule() {
    if (
      !window.confirm(
        `¿Auto-programar las aprobadas en las próximas ${weeks} semanas? ` +
          `Reparte intercalando tipos (mar/jue/sáb, 3/semana).`,
      )
    )
      return;
    setBusy(-2);
    try {
      const res = await post("/biblioteca/admin/blog/api/auto-schedule", {
        weeks,
      });
      const data = (await res.json()) as {
        scheduled?: unknown[];
        skipped?: unknown[];
      };
      const n = data.scheduled?.length ?? 0;
      const s = data.skipped?.length ?? 0;
      alert(`Programadas ${n}.${s ? ` Sin hueco: ${s}.` : ""}`);
      window.location.reload();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(null);
    }
  }

  const proposedF = proposed.filter(matchesFilter);
  const approvedF = approved.filter(matchesFilter);
  const scheduledF = scheduled.filter(matchesFilter);
  const discardedF = discarded.filter(matchesFilter);
  const selCount = [...selected].filter((id) =>
    proposedF.some((p) => p.id === id),
  ).length;

  // Agrupa las programadas por semana natural.
  const byWeek = new Map<string, ProposalItem[]>();
  for (const p of scheduledF) {
    if (!p.scheduled_for) continue;
    const wk = mondayOf(p.scheduled_for);
    (byWeek.get(wk) ?? byWeek.set(wk, []).get(wk)!).push(p);
  }
  const weeksList = [...byWeek.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  const todayIso = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-14">
      {/* ---------- Filtro por tipo ---------- */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mr-1">
          filtro:
        </span>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            data-cursor="hover"
            className={`font-mono text-[10px] tracking-[2px] uppercase border px-3 py-1.5 ${
              filter === f.key
                ? "border-accent text-accent"
                : "border-divider text-ink-dim hover:text-accent"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* ========== ZONA A — Propuestas (validar) ========== */}
      <section>
        <div className="flex items-center justify-between gap-3 flex-wrap mb-1">
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
            1 · Por validar · {proposedF.length}
          </h2>
          {proposedF.length > 0 && (
            <button
              type="button"
              disabled={busy !== null || selCount === 0}
              onClick={() => bulkApprove([...selected])}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
            >
              {busy === -1 ? "aprobando…" : `✓ aprobar en bloque (${selCount})`}
            </button>
          )}
        </div>
        <p className="font-serif italic text-ink-dim text-sm mb-5">
          Revisa y aprueba (o rechaza). Lo aprobado pasa al calendario de abajo.
        </p>
        {proposedF.length === 0 ? (
          <p className="font-serif italic text-ink-faint">
            Nada por validar en este filtro.
          </p>
        ) : (
          <ul className="divide-y divide-divider">
            {proposedF.map((p) => (
              <li key={p.id} className="py-4">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(p.id)}
                    onChange={() => toggleSelected(p.id)}
                    data-cursor="hover"
                    className="mt-1.5 accent-accent w-4 h-4 shrink-0"
                  />
                  <div className="flex-1 min-w-0 flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <Meta p={p} />
                      <Link
                        href={`/biblioteca/admin/blog/${p.id}`}
                        data-cursor="hover"
                        className="block font-serif text-lg text-ink leading-tight hover:text-accent"
                      >
                        {p.title}
                      </Link>
                      {p.angle && (
                        <p className="mt-1 font-serif italic text-ink-dim text-sm leading-relaxed">
                          {p.angle}
                        </p>
                      )}
                      {p.keywords && p.keywords.length > 0 && (
                        <div className="mt-2">
                          <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-1">
                            keywords · {p.keyword_volume.toLocaleString("es-ES")} búsquedas/mes
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {p.keywords
                              .slice()
                              .sort((a, b) => b.volume - a.volume)
                              .slice(0, 8)
                              .map((k) => (
                                <span
                                  key={k.keyword}
                                  className="font-mono text-[10px] text-ink-dim border border-divider px-1.5 py-0.5"
                                >
                                  {k.keyword}{" "}
                                  <span className="text-accent">
                                    {k.volume.toLocaleString("es-ES")}
                                  </span>
                                </span>
                              ))}
                          </div>
                        </div>
                      )}
                      {!p.target_keyword && (
                        <p className="mt-2 font-mono text-[9px] tracking-[2px] uppercase text-accent">
                          ⚠ sin KW objetivo — propuesta antigua, posible canibalización
                        </p>
                      )}
                      {p.source_url && (
                        <a
                          href={p.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono text-[10px] text-accent hover:underline block mt-2"
                        >
                          fuente original ↗
                        </a>
                      )}
                    </div>
                    <div className="shrink-0 flex items-center gap-2 flex-wrap">
                      <button
                        type="button"
                        onClick={() => call("approve", p.id)}
                        disabled={busy === p.id}
                        data-cursor="hover"
                        className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
                      >
                        {busy === p.id ? "generando borrador…" : "aprobar"}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm("¿Rechazar esta propuesta?"))
                            call("discard", p.id);
                        }}
                        disabled={busy === p.id}
                        data-cursor="hover"
                        className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-divider-strong text-ink-faint hover:text-ink px-3 py-1.5 disabled:opacity-40"
                      >
                        rechazar
                      </button>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ========== ZONA B — Calendario (aprobadas) ========== */}
      <section>
        <div className="flex items-center justify-between gap-3 flex-wrap mb-1">
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
            2 · Calendario · {approvedF.length} sin fecha · {scheduledF.length} programadas
          </h2>
          <div className="flex items-center gap-2">
            <label className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
              ventana
              <input
                type="number"
                min={1}
                max={12}
                value={weeks}
                onChange={(e) => setWeeks(Math.max(1, Number(e.target.value) || 1))}
                className="ml-2 w-14 bg-bg border border-divider text-ink font-mono text-[12px] px-2 py-1"
              />
              <span className="ml-1">sem</span>
            </label>
            <button
              type="button"
              disabled={busy !== null || approved.length === 0}
              onClick={autoSchedule}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
            >
              {busy === -2 ? "programando…" : "⚡ auto-programar"}
            </button>
          </div>
        </div>
        <p className="font-serif italic text-ink-dim text-sm mb-5">
          Lo aprobado, listo para fecha. Dale fecha a mano o usa auto-programar
          (intercala tipos, máx 3/semana). Se publica solo al llegar el día.
        </p>

        {/* Aprobadas sin fecha */}
        {approvedF.length === 0 ? (
          <p className="font-serif italic text-ink-faint mb-8">
            Nada aprobado pendiente de fecha.
          </p>
        ) : (
          <ul className="divide-y divide-divider mb-10">
            {approvedF.map((p) => (
              <li key={p.id} className="py-4">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex-1 min-w-0">
                    <Meta p={p} />
                    <Link
                      href={`/biblioteca/admin/blog/${p.id}`}
                      data-cursor="hover"
                      className="block font-serif text-lg text-ink leading-tight hover:text-accent"
                    >
                      {p.title}
                    </Link>
                    <p className="mt-1 font-mono text-[9px] tracking-[2px] uppercase">
                      {p.has_body ? (
                        <span className="text-accent">✓ borrador listo</span>
                      ) : (
                        <span className="text-ink-faint">
                          sin borrador (reintento automático cada pocos min)
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="shrink-0 flex flex-col items-end gap-1">
                    {p.recommended_for && (
                      <p className="font-mono text-[9px] tracking-[1px] uppercase text-accent">
                        sugerido: {fmtDate(p.recommended_for)} (efeméride)
                      </p>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                    <input
                      type="date"
                      min={todayIso}
                      value={dates[p.id] ?? p.recommended_for ?? ""}
                      onChange={(e) =>
                        setDates((d) => ({ ...d, [p.id]: e.target.value }))
                      }
                      className="bg-bg border border-divider text-ink font-mono text-[12px] px-2 py-1.5"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const chosen = dates[p.id] ?? p.recommended_for;
                        chosen
                          ? call("schedule", p.id, { date: chosen })
                          : alert("Elige una fecha primero");
                      }}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
                    >
                      programar
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm("¿Descartar esta propuesta?"))
                          call("discard", p.id);
                      }}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-divider-strong text-ink-faint hover:text-ink px-3 py-1.5 disabled:opacity-40"
                    >
                      descartar
                    </button>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {/* Programadas por semana */}
        <h3 className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-4">
          Programadas
        </h3>
        {weeksList.length === 0 ? (
          <p className="font-serif italic text-ink-dim">
            Nada programado todavía.
          </p>
        ) : (
          <div className="space-y-6">
            {weeksList.map(([wk, items]) => (
              <div key={wk} className="border border-divider p-4">
                <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-3">
                  semana del {fmtDate(wk)} · {items.length}/3
                </p>
                <ul className="space-y-2">
                  {items
                    .slice()
                    .sort((a, b) =>
                      (a.scheduled_for ?? "").localeCompare(b.scheduled_for ?? ""),
                    )
                    .map((p) => (
                      <li
                        key={p.id}
                        className="flex items-start justify-between gap-4 flex-wrap"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="font-mono text-[9px] tracking-[2px] uppercase text-accent">
                            {KIND_LABEL[p.kind] ?? p.kind} ·{" "}
                            {p.scheduled_for && fmtDate(p.scheduled_for)}
                          </p>
                          <Link
                            href={`/biblioteca/admin/blog/${p.id}`}
                            data-cursor="hover"
                            className="block font-serif text-lg text-ink leading-tight hover:text-accent"
                          >
                            {p.title}
                          </Link>
                        </div>
                        <button
                          type="button"
                          onClick={() => call("unschedule", p.id)}
                          disabled={busy === p.id}
                          data-cursor="hover"
                          className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
                        >
                          quitar fecha
                        </button>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ========== Descartadas ========== */}
      {discardedF.length > 0 && (
        <section>
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-1">
            Descartadas · {discardedF.length}
          </h2>
          <p className="font-serif italic text-ink-dim text-sm mb-5">
            Rechazadas. Puedes recuperarlas y vuelven a “por validar”.
          </p>
          <ul className="divide-y divide-divider">
            {discardedF.map((p) => (
              <li
                key={p.id}
                className="py-4 flex items-start justify-between gap-4 flex-wrap opacity-70"
              >
                <div className="flex-1 min-w-0">
                  <Meta p={p} />
                  <Link
                    href={`/biblioteca/admin/blog/${p.id}`}
                    data-cursor="hover"
                    className="block font-serif text-lg text-ink leading-tight hover:text-accent line-through decoration-ink-faint"
                  >
                    {p.title}
                  </Link>
                </div>
                <button
                  type="button"
                  onClick={() => call("restore", p.id)}
                  disabled={busy === p.id}
                  data-cursor="hover"
                  className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
                >
                  recuperar
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Meta({ p }: { p: ProposalItem }) {
  return (
    <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-1">
      {KIND_LABEL[p.kind] ?? p.kind}
      {p.is_longtail && <span className="text-accent"> · long-tail</span>}
      {p.target_keyword && (
        <span className="text-ink-dim">
          {" "}· {p.target_keyword}
          {p.search_volume ? ` (${p.search_volume}/mes)` : ""}
        </span>
      )}
    </p>
  );
}
