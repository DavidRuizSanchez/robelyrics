"use client";

import Link from "next/link";
import { useState } from "react";
import Term from "@/components/admin/Term";
import {
  ActionBar,
  Button,
  Callout,
  Card,
  Details,
  EmptyState,
  Eyebrow,
  Notice,
  Section,
  StatusBadge,
  Toggle,
  cx,
  filterClass,
  inputClass,
} from "@/components/admin/ui";
import { kindLabel } from "@/lib/admin/labels";
import PlacementGroupCard from "./PlacementGroupCard";
import type { PlacementGroup, ProposalItem } from "./page";

// Grupos para el filtro por tipo.
const FILTERS: { key: string; label: string; kinds: Set<string> | null }[] = [
  { key: "all", label: "Todo", kinds: null },
  { key: "actualidad", label: "Actualidad", kinds: new Set(["news"]) },
  {
    key: "efemerides",
    label: "Efemérides",
    kinds: new Set(["anniversary", "album-anniversary"]),
  },
  { key: "spotlight", label: "Análisis de canción", kinds: new Set(["spotlight"]) },
  { key: "evergreen", label: "Temas de fondo", kinds: new Set(["evergreen"]) },
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
  discardedTotal,
}: {
  proposed: ProposalItem[];
  approved: ProposalItem[];
  scheduled: ProposalItem[];
  discarded: ProposalItem[];
  // Total real en BD: `discarded` llega acotado para no pintar 320 filas, así
  // que el número que se enseña no puede salir de `discarded.length`.
  discardedTotal?: number;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [dates, setDates] = useState<Record<number, string>>({});
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState<string>("all");
  const [weeks, setWeeks] = useState<number>(4);
  // Regeneración de titular en la propia lista: id en proceso + candidatos por id.
  const [titleBusy, setTitleBusy] = useState<number | null>(null);
  const [titleCands, setTitleCands] = useState<
    Record<number, { title: string; meta_title: string }[]>
  >({});
  // Edición de título a mano inline (id → texto en edición; ausente = no edita).
  const [titleEdit, setTitleEdit] = useState<Record<number, string>>({});
  // Destino elegido por grupo de keywords (id → índice del grupo → value). Sin
  // elección explícita manda lo que recomienda el análisis.
  const [destino, setDestino] = useState<Record<number, Record<number, string>>>({});
  // Error de la última acción, junto a la pieza que lo provocó (null = general).
  const [error, setError] = useState<{ id: number | null; msg: string } | null>(null);
  const fail = (id: number | null, e: unknown) =>
    setError({ id, msg: String(e).replace(/^Error:\s*/, "") });

  function grupos(p: ProposalItem): PlacementGroup[] {
    return p.placement_groups ?? [];
  }

  function destinoDe(p: ProposalItem, i: number): string {
    const elegido = destino[p.id]?.[i];
    if (elegido) return elegido;
    // Sin recomendación no se escribe un post nuevo por defecto: podría canibalizar
    // la página que ya responde. Mejor quitar las búsquedas, que se reactivan.
    return grupos(p)[i]?.options.find((o) => o.recommended)?.value ?? "skip";
  }

  // ¿Algún grupo va a una página existente u omite keywords? Entonces el botón
  // principal aplica el reparto; si todo va a contenido nuevo, es «aprobar».
  function hayReparto(p: ProposalItem): boolean {
    return grupos(p).some((_, i) => destinoDe(p, i) !== "new");
  }

  async function aplicarReparto(p: ProposalItem) {
    const plan = grupos(p).map((g, i) => ({ keywords: g.keywords, target: destinoDe(p, i) }));
    const resumen = plan
      .map((g) => {
        const opt = grupos(p)
          .flatMap((x) => x.options)
          .find((o) => o.value === g.target);
        const dest =
          g.target === "new" ? "contenido nuevo" : g.target === "skip" ? "se omiten" : (opt?.path ?? g.target);
        return `· ${g.keywords.join(", ")} → ${dest}`;
      })
      .join("\n");
    if (
      !window.confirm(
        `¿Aplicar este reparto?\n\n${resumen}\n\nLas ampliaciones preparan un borrador ` +
          `con el antes/después; no se publica nada hasta que lo apruebes.`,
      )
    )
      return;
    await call("apply-plan", p.id, { groups: plan });
  }

  async function toggleKeyword(p: ProposalItem, keyword: string) {
    const excluidas = new Set(
      p.keywords.filter((k) => k.excluded && !k.merged).map((k) => k.keyword),
    );
    if (excluidas.has(keyword)) excluidas.delete(keyword);
    else excluidas.add(keyword);
    await call("keywords", p.id, { excluded: [...excluidas] });
  }

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
      setError(null);
      await post(`/biblioteca/admin/blog/api/${action}/${id}`, body);
      window.location.reload();
    } catch (e) {
      fail(id, e);
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
      const res = await post("/biblioteca/admin/blog/api/bulk-approve", { ids });
      const data = (await res.json().catch(() => ({}))) as {
        skipped_merge?: number[];
      };
      const saltadas = data.skipped_merge ?? [];
      if (saltadas.length > 0)
        alert(
          `${saltadas.length} no se han aprobado porque el análisis propone ` +
            `AMPLIAR una página existente (#${saltadas.join(", #")}). ` +
            `Decide cada una con su selector: fusionar o contenido nuevo.`,
        );
      window.location.reload();
    } catch (e) {
      fail(null, e);
    } finally {
      setBusy(null);
    }
  }

  async function autoSchedule() {
    if (
      !window.confirm(
        `¿Auto-programar las aprobadas en las próximas ${weeks} semanas? ` +
          `Reparte intercalando tipos (lun/mar/jue/sáb, 4/semana).`,
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
      fail(null, e);
    } finally {
      setBusy(null);
    }
  }

  async function suggestTitle(id: number) {
    setTitleBusy(id);
    try {
      const res = await post(`/biblioteca/admin/blog/api/suggest-titles/${id}`);
      const data = (await res.json()) as {
        candidates?: { title: string; meta_title: string }[];
      };
      setTitleCands((c) => ({ ...c, [id]: data.candidates ?? [] }));
    } catch (e) {
      fail(id, e);
    } finally {
      setTitleBusy(null);
    }
  }

  async function chooseTitle(id: number, title: string) {
    setTitleBusy(id);
    try {
      await post(`/biblioteca/admin/blog/api/title/${id}`, { title });
      window.location.reload();
    } catch (e) {
      fail(id, e);
    } finally {
      setTitleBusy(null);
    }
  }

  async function saveTitle(id: number) {
    const value = (titleEdit[id] ?? "").trim();
    if (!value) return;
    setTitleBusy(id);
    try {
      await post(`/biblioteca/admin/blog/api/title/${id}`, { title: value });
      window.location.reload();
    } catch (e) {
      fail(id, e);
    } finally {
      setTitleBusy(null);
    }
  }

  // Programar con aviso de conflicto: el backend devuelve 409 con el detalle
  // (ya estaba programada / día o semana ocupados / evento tarde). Confirmamos
  // y reenviamos con replace=true.
  async function scheduleProposal(id: number, date: string) {
    setBusy(id);
    try {
      const send = (replace: boolean) =>
        fetch(`/biblioteca/admin/blog/api/schedule/${id}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ date, replace }),
        });
      let res = await send(false);
      if (res.status === 409) {
        const data = await res.json().catch(() => ({}));
        if (!window.confirm(`${data.error}\n\n¿Programar igualmente?`)) return;
        res = await send(true);
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `Error ${res.status}`);
      }
      window.location.reload();
    } catch (e) {
      fail(id, e);
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

  const errorDe = (id: number | null) =>
    error && error.id === id ? (
      <Notice onClose={() => setError(null)}>{error.msg}</Notice>
    ) : null;

  return (
    <div className="space-y-12">
      {errorDe(null)}

      {/* ---------- Filtro por tipo ---------- */}
      <div className="flex flex-wrap gap-2 items-center" role="group" aria-label="Filtrar ideas por tipo">
        <span className="text-sm text-ink-faint mr-1">Mostrar:</span>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={filterClass(filter === f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* ========== Propuestas por validar ========== */}
      <Section
        title="Ideas por decidir"
        count={proposedF.length}
        help="Temas sin escribir. Decide si merecen la pena: lo aprobado pasa al calendario y se escribe cuando llegue su fecha."
        actions={
          proposedF.length > 0 && (
            <Button
              variant="secondary"
              disabled={busy !== null || selCount === 0}
              loading={busy === -1}
              loadingLabel="Aprobando…"
              onClick={() => bulkApprove([...selected])}
              title="Las que proponen ampliar una página se saltan: esas se deciden una a una"
            >
              ✓ Aprobar seleccionadas ({selCount})
            </Button>
          )
        }
      >
        {proposedF.length === 0 ? (
          <EmptyState>Nada por decidir con este filtro.</EmptyState>
        ) : (
          <ul className="space-y-4">
            {proposedF.map((p) => (
              renderProposal(p)
            ))}
          </ul>
        )}
      </Section>

      {/* ========== Aprobadas: calendario ========== */}
      <Section
        title="Ideas aprobadas, sin fecha"
        count={approvedF.length}
        help="Ya validadas. Dales fecha a mano o deja que el calendario las reparta (intercala tipos, máximo 4 por semana). Se escriben y publican solas al llegar el día."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="weeks" className="text-sm text-ink-dim">
              Repartir en
            </label>
            <input
              id="weeks"
              type="number"
              min={1}
              max={12}
              value={weeks}
              onChange={(e) => setWeeks(Math.max(1, Number(e.target.value) || 1))}
              className={cx(inputClass, "w-16 font-mono")}
            />
            <span className="text-sm text-ink-dim">semanas</span>
            <Button
              variant="primary"
              disabled={busy !== null || approved.length === 0}
              loading={busy === -2}
              loadingLabel="Programando…"
              onClick={autoSchedule}
            >
              Programar automáticamente
            </Button>
          </div>
        }
      >
        {approvedF.length === 0 ? (
          <EmptyState>Nada aprobado pendiente de fecha.</EmptyState>
        ) : (
          <ul className="space-y-3">
            {approvedF.map((p) => (
              <Card key={p.id} as="li" tone={p.has_body ? "ok" : "info"}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <Meta p={p} />
                    <TitleLink p={p} />
                    <div className="mt-2 flex flex-wrap gap-2">
                      {p.has_body ? (
                        <StatusBadge tone="ok">✓ Borrador escrito</StatusBadge>
                      ) : (
                        <StatusBadge tone="info" title="Se reintenta solo cada pocos minutos">
                          Escribiéndose…
                        </StatusBadge>
                      )}
                      {forceBadge(p)}
                    </div>
                    {p.recommended_for && (
                      <p className="mt-2 text-sm text-ink-dim">
                        Fecha sugerida: <b className="text-ink">{fmtDate(p.recommended_for)}</b>
                        {p.event_date
                          ? ` (el evento es el ${fmtDate(p.event_date)})`
                          : " (efeméride)"}
                      </p>
                    )}
                  </div>
                </div>
                {errorDe(p.id)}
                <ActionBar
                  primary={
                    <div className="flex flex-wrap items-center gap-2">
                      <label className="sr-only" htmlFor={`fecha-${p.id}`}>
                        Fecha de publicación
                      </label>
                      <input
                        id={`fecha-${p.id}`}
                        type="date"
                        min={todayIso}
                        value={dates[p.id] ?? p.recommended_for ?? ""}
                        onChange={(e) => setDates((d) => ({ ...d, [p.id]: e.target.value }))}
                        className={cx(inputClass, "w-auto font-mono")}
                      />
                      <Button
                        variant="primary"
                        loading={busy === p.id}
                        onClick={() => {
                          const chosen = dates[p.id] ?? p.recommended_for;
                          if (chosen) scheduleProposal(p.id, chosen);
                          else setError({ id: p.id, msg: "Elige una fecha primero." });
                        }}
                      >
                        Programar
                      </Button>
                    </div>
                  }
                  danger={
                    <>
                      {forceToggle(p)}
                      <Button
                        variant="danger"
                        disabled={busy === p.id}
                        onClick={() => {
                          if (window.confirm("¿Descartar esta propuesta?")) call("discard", p.id);
                        }}
                      >
                        Descartar
                      </Button>
                    </>
                  }
                />
              </Card>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Ideas programadas"
        count={scheduledF.length}
        help="Tienen fecha: se escriben y publican solas ese día. Quitarles la fecha las devuelve a «aprobadas»."
      >
        {weeksList.length === 0 ? (
          <EmptyState>Nada programado todavía.</EmptyState>
        ) : (
          <div className="space-y-4">
            {weeksList.map(([wk, items]) => (
              <div key={wk} className="rounded-md border border-divider bg-paper p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <p className="font-medium text-ink">Semana del {fmtDate(wk)}</p>
                  <StatusBadge tone={items.length > 4 ? "danger" : items.length === 4 ? "warn" : "neutral"}>
                    {items.length} de 4 huecos
                  </StatusBadge>
                </div>
                <ul className="divide-y divide-divider">
                  {items
                    .slice()
                    .sort((a, b) => (a.scheduled_for ?? "").localeCompare(b.scheduled_for ?? ""))
                    .map((p) => (
                      <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-ink-dim">
                            <b className="text-ink">{p.scheduled_for && fmtDate(p.scheduled_for)}</b>{" "}
                            · {kindLabel(p.kind)}
                          </p>
                          <TitleLink p={p} small />
                          {errorDe(p.id)}
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={busy === p.id}
                          onClick={() => call("unschedule", p.id)}
                        >
                          Quitar fecha
                        </Button>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* ========== Descartadas ========== */}
      {discardedF.length > 0 && (
        <section>
          {/* Plegada: son cientos y se pintaban enteras, empujando fuera de la
              vista todo lo que venía detrás. Es una papelera, no una cola. */}
          <Details
            summary={
              <span className="text-base text-ink-dim">
                Ideas descartadas{" "}
                <span className="font-mono text-ink-faint">{discardedTotal ?? discardedF.length}</span>
                {(discardedTotal ?? 0) > discardedF.length &&
                  ` · se muestran las ${discardedF.length} más recientes`}
              </span>
            }
          >
            <p className="mb-3 text-sm text-ink-faint">
              Rechazadas. Si recuperas una, vuelve a «Ideas por decidir».
            </p>
            <ul className="divide-y divide-divider">
              {discardedF.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="flex-1 min-w-0 opacity-75">
                    <Meta p={p} />
                    <TitleLink p={p} small />
                    {errorDe(p.id)}
                  </div>
                  <Button size="sm" loading={busy === p.id} onClick={() => call("restore", p.id)}>
                    Recuperar
                  </Button>
                </li>
              ))}
            </ul>
          </Details>
        </section>
      )}
    </div>
  );

  // ── Piezas de la tarjeta (cierran sobre el estado del planner) ────────────
  // Funciones de render, NO componentes: un componente definido aquí dentro
  // sería un tipo nuevo en cada render y React remontaría la tarjeta, así que
  // el campo del titular perdería el foco a cada tecla.

  function forceBadge(p: ProposalItem) {
    return p.force_publish ? (
      <StatusBadge tone="danger">⚡ Se publicará aunque no pase los controles</StatusBadge>
    ) : null;
  }

  function forceToggle(p: ProposalItem) {
    return (
      // El glosario va FUERA del interruptor: un botón dentro de otro no es HTML válido.
      <span className="inline-flex items-center gap-1">
        <Toggle
          pressed={p.force_publish}
          disabled={busy === p.id}
          onClick={() => call("force-publish", p.id)}
          title="Salta el control de calidad y de longitud al publicar"
        >
          Publicar sin controles
        </Toggle>
        <span className="text-xs text-ink-faint">
          <Term k="siOSi">¿qué es?</Term>
        </span>
      </span>
    );
  }

  function renderProposal(p: ProposalItem) {
    const gs = grupos(p);
    const volumes = Object.fromEntries((p.keywords ?? []).map((k) => [k.keyword, k.volume]));
    const kws = (p.keywords ?? []).slice().sort((a, b) => b.volume - a.volume);
    const visibles = kws.slice(0, 8);
    const ocultas = kws.length - visibles.length;
    const reparto = hayReparto(p);
    return (
      <Card key={p.id} as="li" tone="warn">
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={selected.has(p.id)}
            onChange={() => toggleSelected(p.id)}
            aria-label={`Seleccionar «${p.title}» para aprobar en bloque`}
            className="mt-1.5 h-4 w-4 shrink-0 accent-accent"
          />
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <Meta p={p} />
              <StatusBadge tone="warn">Por decidir</StatusBadge>
            </div>

            {/* ── Qué es ── */}
            {p.id in titleEdit ? (
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <label htmlFor={`titulo-${p.id}`} className="sr-only">
                  Titular
                </label>
                <input
                  id={`titulo-${p.id}`}
                  type="text"
                  value={titleEdit[p.id]}
                  onChange={(e) => setTitleEdit((s) => ({ ...s, [p.id]: e.target.value }))}
                  className={cx(inputClass, "flex-1 min-w-[220px] font-serif text-lg")}
                />
                <Button
                  size="sm"
                  variant="primary"
                  loading={titleBusy === p.id}
                  onClick={() => saveTitle(p.id)}
                >
                  Guardar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    setTitleEdit((s) => {
                      const n = { ...s };
                      delete n[p.id];
                      return n;
                    })
                  }
                >
                  Cancelar
                </Button>
              </div>
            ) : (
              <TitleLink p={p} />
            )}
            {p.angle && <p className="mt-1 font-serif italic text-ink-dim">{p.angle}</p>}
            <div className="mt-2 flex flex-wrap gap-2">
              {forceBadge(p)}
              {p.event_date && (
                <StatusBadge tone="info">
                  Evento: {fmtDate(p.event_date)}
                  {p.recommended_for ? ` · sugerido ${fmtDate(p.recommended_for)}` : ""}
                </StatusBadge>
              )}
            </div>
            {!p.target_keyword && (
              <Callout tone="warn" className="mt-3" title="Sin búsqueda objetivo">
                Propuesta antigua: puede pisarse con otra página tuya (
                <Term k="canibalizacion">canibalización</Term>).
              </Callout>
            )}

            {/* ── Búsquedas ── */}
            {kws.length > 0 && (
              <div className="mt-4">
                <Eyebrow>
                  Búsquedas que cubre ·{" "}
                  <span className="font-mono normal-case tracking-normal text-ink-dim">
                    {p.keyword_volume.toLocaleString("es-ES")}
                  </span>{" "}
                  <Term k="volumen">al mes</Term>
                </Eyebrow>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {visibles.map((k) =>
                    k.merged ? (
                      <span
                        key={k.keyword}
                        className="inline-flex items-center gap-1 rounded-md border border-divider px-2 py-1 text-xs text-ink-faint"
                      >
                        <span className="font-mono">{k.keyword}</span> → ya va a{" "}
                        <span className="font-mono">{k.merged}</span>
                      </span>
                    ) : (
                      <button
                        type="button"
                        key={k.keyword}
                        onClick={() => toggleKeyword(p, k.keyword)}
                        disabled={busy !== null}
                        aria-pressed={!k.excluded}
                        title={
                          k.excluded
                            ? "Desactivada: no cuenta. Pulsa para reactivarla"
                            : "Pulsa para desactivarla (demasiado genérica, no encaja…)"
                        }
                        className={cx(
                          "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[13px] transition-colors disabled:opacity-40",
                          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent",
                          k.excluded
                            ? "border-divider text-ink-faint line-through"
                            : "border-divider-strong text-ink hover:border-danger/60",
                        )}
                      >
                        <span className="font-mono">{k.keyword}</span>
                        <span className={cx("font-mono text-xs", k.excluded ? "" : "text-ink-dim")}>
                          {k.volume.toLocaleString("es-ES")}
                        </span>
                      </button>
                    ),
                  )}
                  {ocultas > 0 && (
                    <span className="self-center text-xs text-ink-faint">+{ocultas} más</span>
                  )}
                </div>
                <p className="mt-1 text-xs text-ink-faint">
                  Pulsa una búsqueda para desactivarla si no encaja.
                </p>
              </div>
            )}

            {/* ── Qué propone el sistema ── */}
            {gs.length > 0 && (
              <div className="mt-5">
                <Eyebrow>Qué propone el sistema</Eyebrow>
                <div className="mt-2 space-y-3">
                  {gs.map((g, i) => (
                    <PlacementGroupCard
                      key={g.keywords.join("|")}
                      g={g}
                      volumes={volumes}
                      value={destinoDe(p, i)}
                      onChange={(v) =>
                        setDestino((d) => ({ ...d, [p.id]: { ...(d[p.id] ?? {}), [i]: v } }))
                      }
                      disabled={busy !== null}
                    />
                  ))}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy !== null}
                    onClick={() => call("placement", p.id)}
                    title="Vuelve a calcular el reparto con los datos de Search Console actuales"
                  >
                    ↻ Recalcular con datos actuales
                  </Button>
                </div>
                {p.placement?.last_merge && (
                  <Callout tone="danger" className="mt-2" title="La última fusión no salió">
                    Con <span className="font-mono">{p.placement.last_merge.path}</span> (
                    {p.placement.last_merge.status})
                    {p.placement.last_merge.error ? `: ${p.placement.last_merge.error}` : ""}
                  </Callout>
                )}
              </div>
            )}

            {p.source_url && (
              <a
                href={p.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-block text-sm text-accent hover:underline"
              >
                Ver la fuente original ↗
              </a>
            )}

            {/* ── Titulares alternativos ── */}
            {titleCands[p.id]?.length > 0 && (
              <div className="mt-4 rounded-md border border-divider p-3">
                <Eyebrow>Titulares alternativos</Eyebrow>
                <ul className="mt-2 space-y-2">
                  {titleCands[p.id].map((c, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="flex-1 font-serif text-base text-ink leading-snug">{c.title}</span>
                      <Button
                        size="sm"
                        disabled={titleBusy === p.id}
                        onClick={() => chooseTitle(p.id, c.title)}
                      >
                        Usar este
                      </Button>
                    </li>
                  ))}
                </ul>
                <Button
                  size="sm"
                  variant="ghost"
                  className="mt-2"
                  disabled={titleBusy === p.id}
                  onClick={() => suggestTitle(p.id)}
                >
                  ↻ Proponer otros 3
                </Button>
              </div>
            )}

            {errorDe(p.id)}

            {/* ── Qué haces ── */}
            <ActionBar
              primary={
                reparto ? (
                  <Button
                    variant="primary"
                    loading={busy === p.id}
                    loadingLabel="Preparando…"
                    onClick={() => aplicarReparto(p)}
                    title="Cada grupo de búsquedas a su destino. Las ampliaciones preparan un borrador; no se publica nada."
                  >
                    Aplicar este reparto
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    loading={busy === p.id}
                    loadingLabel="Generando borrador…"
                    onClick={() => call("approve", p.id)}
                  >
                    Aprobar idea
                  </Button>
                )
              }
              secondary={
                <>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy !== null}
                    onClick={() => setTitleEdit((s) => ({ ...s, [p.id]: p.title }))}
                  >
                    ✎ Editar titular
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy !== null}
                    loading={titleBusy === p.id}
                    onClick={() => suggestTitle(p.id)}
                  >
                    ↻ Proponer titulares
                  </Button>
                </>
              }
              danger={
                <>
                  {forceToggle(p)}
                  <Button
                    variant="danger"
                    disabled={busy === p.id}
                    onClick={() => {
                      if (window.confirm("¿Rechazar esta propuesta?")) call("discard", p.id);
                    }}
                  >
                    Rechazar
                  </Button>
                </>
              }
            />
          </div>
        </div>
      </Card>
    );
  }
}

function TitleLink({ p, small }: { p: ProposalItem; small?: boolean }) {
  return (
    <Link
      href={`/biblioteca/admin/blog/${p.id}`}
      className={cx(
        "mt-1 block font-serif text-ink leading-tight hover:text-accent",
        small ? "text-base" : "text-xl",
      )}
    >
      {p.title}
    </Link>
  );
}

function Meta({ p }: { p: ProposalItem }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-dim">
      {/* El id, visible: es lo que cita el aviso de duplicado del alta manual. */}
      <span className="font-mono text-ink-faint">#{p.id}</span>
      <span>{kindLabel(p.kind)}</span>
      {p.is_longtail && <StatusBadge>long-tail</StatusBadge>}
      {p.has_video && <StatusBadge>🎬 con vídeo</StatusBadge>}
      {p.target_keyword && (
        <span>
          · objetivo: <span className="font-mono text-ink">{p.target_keyword}</span>
          {p.search_volume ? (
            <span className="font-mono text-ink-faint"> ({p.search_volume.toLocaleString("es-ES")}/mes)</span>
          ) : null}
        </span>
      )}
    </p>
  );
}
