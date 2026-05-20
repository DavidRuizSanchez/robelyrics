"use client";

import { useState } from "react";
import type { ProposalItem } from "./page";

const KIND_LABEL: Record<string, string> = {
  news: "Noticia",
  anniversary: "Efeméride Robe",
  "album-anniversary": "Aniversario disco",
  spotlight: "Análisis canción",
  evergreen: "Tema de fondo",
};

const ACTUALIDAD = new Set(["news", "anniversary", "album-anniversary"]);

function fmtDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("es-ES", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

// Lunes de la semana natural de una fecha ISO (YYYY-MM-DD).
function mondayOf(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  const day = (d.getDay() + 6) % 7; // 0 = lunes
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}

export default function CalendarioPlanner({
  proposed,
  scheduled,
}: {
  proposed: ProposalItem[];
  scheduled: ProposalItem[];
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [dates, setDates] = useState<Record<number, string>>({});

  async function call(
    action: string,
    id: number,
    body?: Record<string, unknown>,
  ) {
    setBusy(id);
    try {
      const res = await fetch(`/biblioteca/admin/calendario/api/${action}/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || `Error ${res.status}`);
        return;
      }
      window.location.reload();
    } catch (e) {
      alert(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  // Agrupa las programadas por semana natural.
  const byWeek = new Map<string, ProposalItem[]>();
  for (const p of scheduled) {
    if (!p.scheduled_for) continue;
    const wk = mondayOf(p.scheduled_for);
    (byWeek.get(wk) ?? byWeek.set(wk, []).get(wk)!).push(p);
  }
  const weeks = [...byWeek.entries()].sort((a, b) => a[0].localeCompare(b[0]));

  const actualidad = proposed.filter((p) => ACTUALIDAD.has(p.kind));
  const repositorio = proposed.filter((p) => !ACTUALIDAD.has(p.kind));

  const todayIso = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-14">
      {/* ---------- Programadas ---------- */}
      <section>
        <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-5">
          Programadas
        </h2>
        {weeks.length === 0 ? (
          <p className="font-serif italic text-ink-dim">
            Nada programado todavía. Elige propuestas del banco y dales fecha.
          </p>
        ) : (
          <div className="space-y-6">
            {weeks.map(([wk, items]) => (
              <div key={wk} className="border border-divider p-4">
                <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-3">
                  semana del {fmtDate(wk)} · {items.length}/2
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
                          <p className="font-serif text-lg text-ink leading-tight">
                            {p.title}
                          </p>
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

      {/* ---------- Banco ---------- */}
      <ProposalBank
        title="Actualidad"
        subtitle="Noticias y efemérides. El foco editorial."
        items={actualidad}
        busy={busy}
        dates={dates}
        setDates={setDates}
        call={call}
        today={todayIso}
      />
      <ProposalBank
        title="Repositorio de fondo"
        subtitle="Temas evergreen para cuando no hay actualidad."
        items={repositorio}
        busy={busy}
        dates={dates}
        setDates={setDates}
        call={call}
        today={todayIso}
      />
    </div>
  );
}

function ProposalBank({
  title,
  subtitle,
  items,
  busy,
  dates,
  setDates,
  call,
  today,
}: {
  title: string;
  subtitle: string;
  items: ProposalItem[];
  busy: number | null;
  dates: Record<number, string>;
  setDates: React.Dispatch<React.SetStateAction<Record<number, string>>>;
  call: (action: string, id: number, body?: Record<string, unknown>) => void;
  today: string;
}) {
  return (
    <section>
      <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
        {title} · {items.length}
      </h2>
      <p className="font-serif italic text-ink-dim text-sm mb-5">{subtitle}</p>
      {items.length === 0 ? (
        <p className="font-serif italic text-ink-faint">Nada en esta sección.</p>
      ) : (
        <ul className="divide-y divide-divider">
          {items.map((p) => (
            <li key={p.id} className="py-4">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-1">
                    {KIND_LABEL[p.kind] ?? p.kind}
                    {p.source_name && ` · ${p.source_name}`}
                  </p>
                  <p className="font-serif text-lg text-ink leading-tight">
                    {p.title}
                  </p>
                  {p.angle && (
                    <p className="mt-1 font-serif italic text-ink-dim text-sm leading-relaxed">
                      {p.angle}
                    </p>
                  )}
                  {p.keywords && p.keywords.length > 0 && (
                    <div className="mt-2">
                      <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-1">
                        keywords · {p.keyword_volume.toLocaleString("es-ES")}{" "}
                        búsquedas/mes
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
                  {p.source_url && (
                    <a
                      href={p.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-[10px] text-accent hover:underline"
                    >
                      fuente original ↗
                    </a>
                  )}
                </div>
                <div className="shrink-0 flex items-center gap-2 flex-wrap">
                  <input
                    type="date"
                    min={today}
                    value={dates[p.id] ?? ""}
                    onChange={(e) =>
                      setDates((d) => ({ ...d, [p.id]: e.target.value }))
                    }
                    className="bg-bg border border-divider text-ink font-mono text-[12px] px-2 py-1.5"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      dates[p.id]
                        ? call("schedule", p.id, { date: dates[p.id] })
                        : alert("Elige una fecha primero")
                    }
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
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
