"use client";

import { useState } from "react";

const TARGETS: { value: string; label: string }[] = [
  { value: "song_lyrics", label: "La letra" },
  { value: "authorship", label: "La autoría" },
  { value: "catalog", label: "El disco o el año" },
  { value: "interpretation", label: "La interpretación" },
];

export default function ReportErrata({ songId }: { songId: number }) {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState("song_lyrics");
  const [wrong, setWrong] = useState("");
  const [right, setRight] = useState("");
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!wrong.trim() && !right.trim() && !note.trim()) return;
    setState("sending");
    try {
      const res = await fetch("/biblioteca/api/errata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: target,
          target_id: songId,
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

  if (state === "done") {
    return (
      <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-dim mt-4 leading-relaxed">
        {msg}
      </p>
    );
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        data-cursor="hover"
        className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint hover:text-accent transition-colors mt-4"
      >
        ¿Ves algo mal? Avísanos
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="mt-4 max-w-[520px] border-l-2 border-accent/40 pl-4 py-2 space-y-3">
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
        Reportar una errata
      </p>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {TARGETS.map((t) => (
          <label key={t.value} className="font-mono text-[10px] tracking-[1px] uppercase text-ink-dim cursor-pointer">
            <input
              type="radio"
              name="target"
              value={t.value}
              checked={target === t.value}
              onChange={() => setTarget(t.value)}
              className="mr-1 accent-[#a83a3a]"
            />
            {t.label}
          </label>
        ))}
      </div>
      <input
        value={wrong}
        onChange={(e) => setWrong(e.target.value)}
        placeholder="Lo que pone (y está mal)"
        className="w-full bg-transparent border-b border-divider focus:border-accent focus:outline-none px-0 py-1.5 font-serif text-[15px] text-ink placeholder:text-ink-faint"
      />
      <input
        value={right}
        onChange={(e) => setRight(e.target.value)}
        placeholder="Lo que debería poner"
        className="w-full bg-transparent border-b border-divider focus:border-accent focus:outline-none px-0 py-1.5 font-serif text-[15px] text-ink placeholder:text-ink-faint"
      />
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Nota (opcional): fuente, contexto…"
        className="w-full bg-transparent border-b border-divider focus:border-accent focus:outline-none px-0 py-1.5 font-serif text-[15px] text-ink placeholder:text-ink-faint"
      />
      <div className="flex items-center gap-4 pt-1">
        <button
          type="submit"
          disabled={state === "sending"}
          data-cursor="hover"
          className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 font-mono text-[10px] tracking-[2px] uppercase px-4 py-1.5 transition-colors"
        >
          {state === "sending" ? "Enviando…" : "Enviar aviso"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          data-cursor="hover"
          className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint hover:text-ink"
        >
          Cancelar
        </button>
        {state === "error" && (
          <span className="font-mono text-[10px] tracking-[1px] uppercase text-accent">{msg}</span>
        )}
      </div>
    </form>
  );
}
