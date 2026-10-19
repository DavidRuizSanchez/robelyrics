"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Eyebrow, Notice, cx, inputClass } from "@/components/admin/ui";

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
      <label htmlFor="titular" className="sr-only">
        Titular
      </label>
      <textarea
        id="titular"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        rows={2}
        className={cx(inputClass, "font-serif text-3xl md:text-4xl leading-[1.15] resize-none")}
      />

      <div className="flex items-center gap-2 flex-wrap">
        <Button
          variant="primary"
          size="sm"
          onClick={() => save(title)}
          disabled={busy !== null || !dirty}
          loading={busy === "save"}
          loadingLabel="Guardando…"
        >
          Guardar titular
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={suggest}
          disabled={busy !== null}
          loading={busy === "suggest"}
          loadingLabel="Pensando…"
        >
          {candidates.length ? "↻ Proponer otros 3" : "↻ Proponer 3 titulares"}
        </Button>
        {dirty && <span className="text-sm text-warn">Cambios sin guardar</span>}
      </div>

      {error && <Notice onClose={() => setError(null)}>{error}</Notice>}

      {candidates.length > 0 && (
        <div className="rounded-md border border-divider p-3">
          <Eyebrow>Alternativas · pulsa una para probarla</Eyebrow>
          <ul className="mt-2 space-y-2">
            {candidates.map((c, i) => (
              <li key={i} className="flex items-start gap-3">
                <button
                  type="button"
                  onClick={() => setTitle(c.title)}
                  className="flex-1 text-left font-serif text-lg text-ink hover:text-accent leading-snug"
                >
                  {c.title}
                </button>
                <Button size="sm" disabled={busy !== null} onClick={() => save(c.title)}>
                  Usar este
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
