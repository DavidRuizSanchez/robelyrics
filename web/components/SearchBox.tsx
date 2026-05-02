"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition, type FormEvent } from "react";

type Mode = "semantic" | "complete";

export default function SearchBox({
  initialQuery = "",
  initialMode = "semantic",
}: {
  initialQuery?: string;
  initialMode?: Mode;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [query, setQuery] = useState(initialQuery);
  const [isPending, startTransition] = useTransition();

  // Sincronizar el state con la URL: si el usuario navega a / sin query
  // (ej. click en "RobeLyrics" del header), reseteamos el campo.
  useEffect(() => {
    setQuery(initialQuery);
    setMode(initialMode);
  }, [initialQuery, initialMode]);

  function navigate(nextMode: Mode, nextQuery: string) {
    if (!nextQuery.trim()) return;
    const sp = new URLSearchParams(params.toString());
    sp.set("q", nextQuery.trim());
    sp.set("mode", nextMode);
    startTransition(() => {
      router.push(`/?${sp.toString()}`);
    });
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    navigate(mode, query);
  }

  function onModeChange(nextMode: Mode) {
    setMode(nextMode);
    // Si ya hay una query escrita, re-disparamos en el nuevo modo
    if (query.trim()) navigate(nextMode, query);
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-3xl mx-auto">
      <div className="flex gap-2 mb-4 justify-center">
        <ModeButton
          active={mode === "semantic"}
          onClick={() => onModeChange("semantic")}
          label="Encuentra el equivalente"
          hint='"se acabó lo bonito" → "se acabaron las flores"'
        />
        <ModeButton
          active={mode === "complete"}
          onClick={() => onModeChange("complete")}
          label="Completa la frase"
          hint='"abre la puerta" → "que soy el diablo..."'
        />
      </div>

      <div className="relative">
        <input
          type="text"
          name="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={
            mode === "semantic"
              ? "Escribe una frase de la vida real…"
              : "Empieza una línea para que la complete…"
          }
          autoFocus
          className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-5 py-4 text-lg text-zinc-100 focus:outline-none focus:border-zinc-600 placeholder-zinc-600"
        />
        <button
          type="submit"
          disabled={!query.trim()}
          className="absolute right-2 top-1/2 -translate-y-1/2 bg-zinc-100 text-zinc-950 font-semibold rounded-md px-4 py-2 hover:bg-white transition disabled:opacity-40 flex items-center gap-2"
        >
          {isPending && (
            <span className="inline-block w-3 h-3 border-2 border-zinc-950/30 border-t-zinc-950 rounded-full animate-spin" />
          )}
          {isPending ? "Buscando" : "Buscar"}
        </button>
      </div>
    </form>
  );
}

function ModeButton({
  active,
  onClick,
  label,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 rounded-lg text-sm transition ${
        active
          ? "bg-zinc-100 text-zinc-950 font-semibold"
          : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
      }`}
      title={hint}
    >
      {label}
    </button>
  );
}
