"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Un alta manual tarda 2-4 min (investiga, escribe y la juzga el editor jefe), así
// que no se espera a que termine: el servidor la ejecuta en segundo plano y aquí se
// pregunta por ella. Cerrar la pestaña ya no la cancela.
type Job = {
  id: number;
  status: "running" | "done" | "rejected" | "failed";
  url: string;
  proposal_id: number | null;
  title: string | null;
  rewritten: boolean;
  warning: string | null;
  score: number | null;
  reasons: string[];
  boosted: boolean;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

const ENDPOINT = "/biblioteca/admin/blog/api/ingest-url";

export default function UrlIngestForm() {
  const [url, setUrl] = useState("");
  const [topic, setTopic] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [rewrite, setRewrite] = useState(true);
  const [force, setForce] = useState(false);
  const [sending, setSending] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const running = job?.status === "running";
  const busy = sending || running;

  // Errores en los que la salida es pegar el texto: se abre el campo y se señala,
  // en vez de dejar al admin con un código HTTP a secas.
  const failMsg = job?.status === "failed" ? job.error || "" : error || "";
  const needsPaste = /bloquea la descarga|muro de pago|«cuerpo del artículo»/.test(failMsg);

  const poll = useCallback(async (id: number) => {
    try {
      const res = await fetch(`${ENDPOINT}?limit=20`, { cache: "no-store" });
      const jobs: Job[] = res.ok ? await res.json() : [];
      const found = jobs.find((j) => j.id === id);
      if (found) {
        setJob(found);
        if (found.status === "running") timer.current = setTimeout(() => poll(id), 4000);
      } else {
        timer.current = setTimeout(() => poll(id), 4000);
      }
    } catch {
      timer.current = setTimeout(() => poll(id), 8000);
    }
  }, []);

  // Al cargar la página: si quedó un trabajo corriendo (cerraste la pestaña, te
  // fuiste a otra sección), se retoma su seguimiento donde estaba.
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await fetch(`${ENDPOINT}?limit=5`, { cache: "no-store" });
        if (!res.ok) return;
        const jobs: Job[] = await res.json();
        const enCurso = jobs.find((j) => j.status === "running");
        if (vivo && enCurso) {
          setJob(enCurso);
          poll(enCurso.id);
        }
      } catch {
        /* el panel funciona igual sin esto */
      }
    })();
    return () => {
      vivo = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [poll]);

  // `forceOverride` para el botón «guardarla igualmente»: setForce(true) no se ve
  // en este mismo tick, así que el valor viaja por parámetro.
  async function submit(forceOverride?: boolean) {
    const clean = url.trim();
    if (!clean) return;
    const forceNow = forceOverride ?? force;
    setSending(true);
    setError(null);
    setJob(null);
    try {
      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: clean,
          topic: topic.trim() || undefined,
          body_text: bodyText.trim() || undefined,
          rewrite,
          force: forceNow,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || `Error ${res.status}`);
      } else {
        setJob(data as Job);
        poll((data as Job).id);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <details className="border border-divider mt-8">
      <summary
        data-cursor="hover"
        className="cursor-pointer select-none px-5 py-3 font-mono text-[10px] tracking-[2.5px] uppercase text-accent"
      >
        + añadir al banco desde una URL
      </summary>

      <div className="px-5 pb-6 pt-2 space-y-5 border-t border-divider">
        <p className="font-serif italic text-ink-dim text-sm">
          Pega un enlace y entra en «por validar» como una noticia más. Con la
          reescritura editorial investiga, escribe con nuestra voz y verifica los
          datos (tarda 1-2 min); sin ella, guarda el texto tal cual.
        </p>

        <div>
          <label
            htmlFor="ingest-url"
            className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
          >
            URL del artículo *
          </label>
          <input
            id="ingest-url"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
            className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif text-base text-ink"
          />
        </div>

        <div>
          <label
            htmlFor="ingest-topic"
            className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
          >
            Tema (opcional)
          </label>
          <input
            id="ingest-topic"
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Pista del protagonista si el título no basta"
            className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif text-base text-ink"
          />
        </div>

        <div>
          <label
            htmlFor="ingest-body"
            className={`block font-mono text-[10px] tracking-[2px] uppercase mb-1.5 ${
              needsPaste ? "text-accent" : "text-ink-dim"
            }`}
          >
            Cuerpo del artículo (opcional)
          </label>
          <p className="font-serif italic text-ink-dim text-sm mb-2">
            Solo si el medio no deja descargarlo (error 406/403) o lo esconde
            tras un muro de pago: abre el enlace, copia el texto y pégalo aquí.
            Se usa en lugar de la descarga; lo demás va igual.
          </p>
          <textarea
            id="ingest-body"
            value={bodyText}
            onChange={(e) => setBodyText(e.target.value)}
            rows={bodyText || needsPaste ? 8 : 3}
            placeholder="Pega aquí el texto del artículo…"
            className={`w-full bg-transparent border ${
              needsPaste ? "border-accent" : "border-divider"
            } focus:border-accent focus:outline-none px-3 py-2 font-serif text-base text-ink leading-relaxed resize-y`}
          />
          {bodyText.trim() && (
            <p className="mt-1 font-mono text-[10px] tracking-[1px] text-ink-dim">
              {bodyText.trim().length} caracteres · se ignorará la descarga
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-6">
          <label className="flex items-center gap-2 font-mono text-[11px] tracking-[1px] text-ink-dim" data-cursor="hover">
            <input
              type="checkbox"
              checked={rewrite}
              onChange={(e) => setRewrite(e.target.checked)}
              className="accent-accent w-4 h-4"
            />
            reescribir con voz editorial
          </label>
          <label className="flex items-center gap-2 font-mono text-[11px] tracking-[1px] text-ink-dim" data-cursor="hover">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="accent-accent w-4 h-4"
            />
            forzar (repetir tema, o retomar una descartada)
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={() => submit()}
            disabled={busy || !url.trim()}
            data-cursor="hover"
            className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-40 disabled:cursor-not-allowed font-mono text-[11px] tracking-[3px] uppercase px-7 py-3 transition-colors"
          >
            {running
              ? "trabajando en el servidor…"
              : sending
                ? "encolando…"
                : "añadir al banco"}
          </button>
          {/* Sin URL el botón queda muerto: decir por qué, que si no parece roto. */}
          {!busy && !url.trim() && (
            <p className="font-mono text-[10px] tracking-[1px] text-ink-faint">
              falta la URL del artículo
            </p>
          )}
        </div>

        {/* EN CURSO. El trabajo vive en el servidor: se puede cerrar la pestaña y
            al volver se retoma el seguimiento solo. */}
        {running && (
          <div className="border border-divider p-4 space-y-1">
            <p className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
              ⟳ trabajo #{job!.id} en marcha
            </p>
            <p className="font-serif italic text-ink-dim text-sm leading-relaxed">
              Investigando, escribiendo y pasándola por el editor jefe. Tarda entre 2
              y 4 minutos. Corre en el servidor: puedes cerrar esta página o irte a
              otra sección — al volver seguirá aquí.
            </p>
          </div>
        )}

        {/* Fallos: los del envío y los que registra el propio trabajo. */}
        {!!failMsg && (
          <p className="text-accent font-mono text-xs tracking-[1px]">✗ {failMsg}</p>
        )}

        {/* Rechazo del gate de rigor: se muestra por qué, que es lo único que
            permite decidir si merece la pena buscar más material o soltarla. */}
        {job?.status === "rejected" && (
          <div className="border border-accent/40 bg-accent/5 p-4 space-y-2">
            <p className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
              ✗ no se ha creado la propuesta
              {typeof job.score === "number" ? ` · rigor ${job.score}/100` : ""}
            </p>
            <p className="font-serif text-base text-ink leading-snug">
              El editor jefe la rechaza: no hay material para un artículo que aporte
              algo.
            </p>
            <ul className="list-none space-y-1">
              {job.reasons.map((r, i) => (
                <li key={i} className="font-serif italic text-ink-dim text-sm leading-relaxed">
                  · {r}
                </li>
              ))}
            </ul>
            <p className="font-mono text-[10px] tracking-[1px] text-ink-faint">
              {job.boosted
                ? "se reintentó con investigación reforzada y siguió sin dar de sí"
                : "no se pudo reescribir ni con refuerzo"}
              . Si tienes más material (entrevista, fotos, datos), añádelo al cuerpo y
              vuelve a intentarlo.
            </p>
            <button
              type="button"
              onClick={() => {
                setForce(true);
                setUrl(job.url);
                submit(true);
              }}
              disabled={busy}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
            >
              guardarla igualmente
            </button>
          </div>
        )}

        {job?.status === "done" && (
          <div className="border border-accent/30 bg-accent/5 p-4 space-y-2">
            <p className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
              ✓ propuesta #{job.proposal_id} creada
              {job.rewritten ? " · reescrita" : " · texto en crudo"}
            </p>
            <p className="font-serif text-base text-ink leading-snug">{job.title}</p>
            {job.warning && (
              <p className="font-mono text-[11px] tracking-[0.5px] text-accent">
                ⚠ {job.warning}
              </p>
            )}
            <button
              type="button"
              onClick={() => window.location.reload()}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5"
            >
              recargar para verla en «por validar»
            </button>
          </div>
        )}
      </div>
    </details>
  );
}
