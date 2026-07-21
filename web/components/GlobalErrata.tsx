"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";

const TARGETS: { value: string; label: string }[] = [
  { value: "content", label: "El texto" },
  { value: "song_lyrics", label: "La letra" },
  { value: "authorship", label: "La autoría" },
  { value: "catalog", label: "El disco o el año" },
  { value: "interpretation", label: "La interpretación" },
];

// Widget de erratas presente en TODAS las páginas (via layout). Discreto abajo a
// la derecha; captura la ruta actual para que el admin sepa dónde.
export default function GlobalErrata() {
  const pathname = usePathname() || "/";
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState("content");
  const [wrong, setWrong] = useState("");
  const [right, setRight] = useState("");
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  // No molestar en el admin (allí se gestionan, no se reportan).
  if (pathname.startsWith("/biblioteca/admin")) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!wrong.trim() && !right.trim() && !note.trim()) return;
    setState("sending");
    try {
      const res = await fetch("/api/errata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: target,
          page_ref: pathname,
          reported_wrong: wrong.trim() || null,
          suggested_right: right.trim() || null,
          note: note.trim() || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "error");
      setState("done");
      setMsg(data.message || "Gracias por el aviso.");
    } catch (err) {
      setState("error");
      setMsg(err instanceof Error ? err.message : "No se pudo enviar.");
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 print:hidden">
      {!open ? (
        <button
          onClick={() => {
            setOpen(true);
            setState("idle");
          }}
          data-cursor="hover"
          aria-label="Reportar una errata"
          className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint hover:text-accent bg-bg-deep/85 backdrop-blur border border-divider hover:border-accent px-3 py-2 transition-colors"
        >
          ¿Ves algo mal?
        </button>
      ) : (
        <div className="w-[320px] max-w-[calc(100vw-2rem)] bg-bg-deep/95 backdrop-blur border border-divider p-4 shadow-xl">
          {state === "done" ? (
            <div className="space-y-3">
              <p className="font-serif italic text-[14px] text-ink leading-relaxed">{msg}</p>
              <button
                onClick={() => setOpen(false)}
                data-cursor="hover"
                className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint hover:text-ink"
              >
                Cerrar
              </button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="font-mono text-[10px] tracking-[2px] uppercase text-accent">Reportar errata</p>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  data-cursor="hover"
                  className="font-mono text-[12px] text-ink-faint hover:text-ink"
                  aria-label="Cerrar"
                >
                  ×
                </button>
              </div>
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                className="w-full bg-transparent border border-divider focus:border-accent focus:outline-none px-2 py-1.5 font-mono text-[10px] tracking-[1px] uppercase text-ink-dim"
              >
                {TARGETS.map((t) => (
                  <option key={t.value} value={t.value} className="bg-bg-deep">
                    {t.label}
                  </option>
                ))}
              </select>
              <input
                value={wrong}
                onChange={(e) => setWrong(e.target.value)}
                placeholder="Lo que pone (y está mal)"
                className="w-full bg-transparent border-b border-divider focus:border-accent focus:outline-none px-0 py-1.5 font-serif text-[14px] text-ink placeholder:text-ink-faint"
              />
              <input
                value={right}
                onChange={(e) => setRight(e.target.value)}
                placeholder="Lo que debería poner"
                className="w-full bg-transparent border-b border-divider focus:border-accent focus:outline-none px-0 py-1.5 font-serif text-[14px] text-ink placeholder:text-ink-faint"
              />
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Nota (opcional): fuente, contexto…"
                className="w-full bg-transparent border-b border-divider focus:border-accent focus:outline-none px-0 py-1.5 font-serif text-[14px] text-ink placeholder:text-ink-faint"
              />
              <div className="flex items-center gap-3 pt-1">
                <button
                  type="submit"
                  disabled={state === "sending"}
                  data-cursor="hover"
                  className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 font-mono text-[10px] tracking-[2px] uppercase px-3 py-1.5 transition-colors"
                >
                  {state === "sending" ? "Enviando…" : "Enviar"}
                </button>
                {state === "error" && (
                  <span className="font-mono text-[9px] tracking-[1px] uppercase text-accent">{msg}</span>
                )}
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
