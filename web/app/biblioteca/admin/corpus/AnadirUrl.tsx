"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, Field, Notice, inputClass } from "@/components/admin/ui";

// Cómo entra. Mismo vocabulario que `CORPUS_KIND`, en corto para un selector.
const TIPOS: { value: string; label: string }[] = [
  { value: "youtube_transcript", label: "Análisis de un fan (Juancares, Tesônica…)" },
  { value: "media_report", label: "Reportaje de un medio (fondo)" },
  { value: "entorno_interview", label: "Entrevista a alguien del entorno" },
  { value: "robe_interview", label: "Habla Robe" },
];

export default function AnadirUrl() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [tipo, setTipo] = useState(TIPOS[0].value);
  const [titulo, setTitulo] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const esYoutube = /youtu\.?be/.test(url);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const res = await fetch("/biblioteca/admin/corpus/api/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), tipo, titulo: titulo.trim() || null }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string; mensaje?: string };
      if (!res.ok) throw new Error(data.error || "No se pudo añadir.");
      setOk(data.mensaje ?? "Añadido.");
      setUrl("");
      setTitulo("");
      router.refresh();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "No se pudo añadir.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={enviar} className="space-y-3">
        <Field
          label="URL"
          htmlFor="corpus-url"
          hint="Un vídeo de YouTube o un audio que yt-dlp sepa bajar. Entra aprobado, va el primero y no gasta hueco de la semana."
        >
          <input
            id="corpus-url"
            className={inputClass}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=…"
            required
          />
        </Field>
        <Field label="Cómo entra" htmlFor="corpus-tipo">
          <select id="corpus-tipo" className={inputClass} value={tipo} onChange={(e) => setTipo(e.target.value)}>
            {TIPOS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>
        {url && !esYoutube && (
          <Field label="Título" htmlFor="corpus-titulo" hint="Fuera de YouTube no hay de dónde sacarlo.">
            <input
              id="corpus-titulo"
              className={inputClass}
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              required
            />
          </Field>
        )}
        <Button variant="primary" type="submit" loading={busy} loadingLabel="Añadiendo…" disabled={busy || !url}>
          Añadir al corpus
        </Button>
        {ok && <p className="text-sm text-ok">{ok}</p>}
        {err && <Notice onClose={() => setErr(null)}>{err}</Notice>}
      </form>
    </Card>
  );
}
