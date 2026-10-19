"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Callout,
  Field,
  JobStatus,
  Notice,
  cx,
  inputClass,
} from "@/components/admin/ui";

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
    <details className="rounded-md border border-divider bg-paper">
      <summary className="cursor-pointer select-none list-none px-4 py-3 text-ink hover:bg-paper-hi rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden">
        <span className="font-medium">＋ Añadir una noticia desde un enlace</span>
        <span className="ml-2 text-sm text-ink-faint">entra como idea por decidir</span>
      </summary>

      <div className="px-4 pb-5 pt-4 space-y-5 border-t border-divider">
        <p className="text-sm text-ink-dim max-w-2xl">
          Pega un enlace y entra en «Ideas por decidir» como una noticia más. Si la reescribes,
          investiga, escribe con nuestra voz y verifica los datos (tarda 2-4 min); si no, guarda
          el texto tal cual.
        </p>

        <Field label="Enlace del artículo *" htmlFor="ingest-url">
          <input
            id="ingest-url"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
            className={cx(inputClass, "font-mono")}
          />
        </Field>

        <Field
          label="Tema (opcional)"
          htmlFor="ingest-topic"
          hint="Una pista del protagonista si el título no basta."
        >
          <input
            id="ingest-topic"
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className={inputClass}
          />
        </Field>

        <Field
          label={
            <span className={needsPaste ? "text-warn" : undefined}>
              Texto del artículo (opcional){needsPaste ? " — hace falta pegarlo" : ""}
            </span>
          }
          htmlFor="ingest-body"
          hint={
            bodyText.trim()
              ? `${bodyText.trim().length} caracteres · se usa en lugar de descargar el enlace`
              : "Solo si el medio no deja descargarlo (error 406/403) o tiene muro de pago: abre el enlace, copia el texto y pégalo aquí."
          }
        >
          <textarea
            id="ingest-body"
            value={bodyText}
            onChange={(e) => setBodyText(e.target.value)}
            rows={bodyText || needsPaste ? 8 : 3}
            placeholder="Pega aquí el texto del artículo…"
            className={cx(inputClass, "font-serif text-base leading-relaxed resize-y", needsPaste && "border-warn")}
          />
        </Field>

        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm text-ink-dim">
            <input
              type="checkbox"
              checked={rewrite}
              onChange={(e) => setRewrite(e.target.checked)}
              className="accent-accent w-4 h-4"
            />
            Reescribirla con nuestra voz (recomendado)
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-dim">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="accent-accent w-4 h-4"
            />
            Forzar: aunque el tema ya exista o se hubiera descartado
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            onClick={() => submit()}
            disabled={busy || !url.trim()}
            loading={busy}
            loadingLabel={running ? "Trabajando en el servidor…" : "Encolando…"}
          >
            Añadir al banco de ideas
          </Button>
          {/* Sin URL el botón queda muerto: decir por qué, que si no parece roto. */}
          {!busy && !url.trim() && <p className="text-sm text-ink-faint">Falta el enlace.</p>}
        </div>

        {/* EN CURSO. El trabajo vive en el servidor: se puede cerrar la pestaña y
            al volver se retoma el seguimiento solo. */}
        {running && (
          <div className="space-y-2">
            <JobStatus
              label={`Trabajo #${job!.id} en marcha`}
              hint="tarda entre 2 y 4 minutos"
            />
            <p className="text-sm text-ink-dim">
              Investigando, escribiendo y pasándola por el editor jefe. Corre en el servidor:
              puedes cerrar esta página y al volver seguirá aquí.
            </p>
          </div>
        )}

        {/* Fallos: los del envío y los que registra el propio trabajo. */}
        {!!failMsg && <Notice>{failMsg}</Notice>}

        {/* Rechazo del gate de rigor: se muestra por qué, que es lo único que
            permite decidir si merece la pena buscar más material o soltarla. */}
        {job?.status === "rejected" && (
          <Callout
            tone="danger"
            title={`No se ha creado la idea${
              typeof job.score === "number" ? ` · rigor ${job.score}/100` : ""
            }`}
          >
            <p>El editor jefe la rechaza: no hay material para un artículo que aporte algo.</p>
            <ul className="mt-2 list-disc pl-5 space-y-1">
              {job.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-ink-faint">
              {job.boosted
                ? "Se reintentó con investigación reforzada y siguió sin dar de sí."
                : "No se pudo reescribir ni con refuerzo."}{" "}
              Si tienes más material (entrevista, fotos, datos), añádelo al texto y vuelve a
              intentarlo.
            </p>
            <Button
              size="sm"
              variant="danger"
              className="mt-3"
              onClick={() => {
                setForce(true);
                setUrl(job.url);
                submit(true);
              }}
              disabled={busy}
            >
              Guardarla igualmente
            </Button>
          </Callout>
        )}

        {job?.status === "done" && (
          <Callout
            tone="ok"
            title={`✓ Idea #${job.proposal_id} creada${job.rewritten ? " y reescrita" : " con el texto en crudo"}`}
          >
            <p className="font-serif text-base text-ink">{job.title}</p>
            {job.warning && <p className="mt-1 text-warn">⚠ {job.warning}</p>}
            <Button size="sm" className="mt-2" onClick={() => window.location.reload()}>
              Recargar para verla
            </Button>
          </Callout>
        )}
      </div>
    </details>
  );
}
