"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Candidate = { title: string; meta_title: string };

export default function TitleEditor({
  id,
  initialTitle,
}: {
  id: number;
  initialTitle: string;
}) {
  const router = useRouter();
  const [title, setTitle] = useState(initialTitle);
  const [savedTitle, setSavedTitle] = useState(initialTitle);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState<null | "save" | "suggest">(null);
  const [error, setError] = useState<string | null>(null);

  const dirty = title.trim() !== savedTitle.trim();

  async function suggest() {
    setBusy("suggest");
    setError(null);
    try {
      const res = await fetch(`/biblioteca/admin/blog/api/suggest-titles/${id}`, {
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || `Error ${res.status}`);
        return;
      }
      setCandidates(data.candidates ?? []);
    } catch (e) {
      setError(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  async function save(value: string) {
    const clean = value.trim();
    if (!clean) {
      setError("el titular no puede estar vacío");
      return;
    }
    setBusy("save");
    setError(null);
    try {
      const res = await fetch(`/biblioteca/admin/blog/api/title/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: clean }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || `Error ${res.status}`);
        return;
      }
      setSavedTitle(clean);
      setTitle(clean);
      setCandidates([]);
      router.refresh();
    } catch (e) {
      setError(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      <textarea
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        rows={2}
        className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-1 font-serif text-3xl md:text-4xl text-ink leading-[1.15] resize-none"
      />

      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => save(title)}
          disabled={busy !== null || !dirty}
          data-cursor="hover"
          className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
        >
          {busy === "save" ? "guardando…" : "guardar titular"}
        </button>
        <button
          type="button"
          onClick={suggest}
          disabled={busy !== null}
          data-cursor="hover"
          className="font-mono text-[10px] tracking-[2px] uppercase border border-divider text-ink-dim hover:border-accent hover:text-accent px-3 py-1.5 disabled:opacity-40"
        >
          {busy === "suggest"
            ? "pensando…"
            : candidates.length
              ? "↻ otras 3"
              : "↻ proponer 3 con IA"}
        </button>
        {dirty && (
          <span className="font-mono text-[9px] tracking-[1px] uppercase text-ink-faint">
            sin guardar
          </span>
        )}
      </div>

      {error && (
        <p className="text-accent font-mono text-xs tracking-[1px]">✗ {error}</p>
      )}

      {candidates.length > 0 && (
        <ul className="space-y-2 border border-divider p-3">
          <li className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
            alternativas · pulsa para usar
          </li>
          {candidates.map((c, i) => (
            <li key={i} className="flex items-start gap-3">
              <button
                type="button"
                onClick={() => setTitle(c.title)}
                data-cursor="hover"
                className="text-left font-serif text-lg text-ink hover:text-accent leading-snug"
              >
                {c.title}
              </button>
              <button
                type="button"
                onClick={() => save(c.title)}
                disabled={busy !== null}
                data-cursor="hover"
                className="shrink-0 font-mono text-[9px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-2 py-1 disabled:opacity-40"
              >
                usar
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
