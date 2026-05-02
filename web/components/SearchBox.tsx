"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  useTransition,
  type FormEvent,
} from "react";

type Mode = "semantic" | "complete";

const PLACEHOLDERS: Record<Mode, string> = {
  semantic: "Escribe lo que sientes…",
  complete: "Empieza una línea…",
};

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
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Sincroniza state con URL (reset al volver a /, o cambio de modo desde nav)
  useEffect(() => {
    setQuery(initialQuery);
    setMode(initialMode);
  }, [initialQuery, initialMode]);

  // Focus al cambiar modo
  useEffect(() => {
    inputRef.current?.focus();
  }, [mode]);

  function navigate(nextMode: Mode, nextQuery: string) {
    if (!nextQuery.trim()) return;
    const sp = new URLSearchParams(params.toString());
    sp.set("q", nextQuery.trim());
    sp.set("mode", nextMode);
    startTransition(() => {
      router.push(`/?${sp.toString()}#search`);
    });
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    navigate(mode, query);
  }

  function onModeChange(nextMode: Mode) {
    setMode(nextMode);
    if (query.trim()) navigate(nextMode, query);
    else {
      // Cambia URL sin query para que el header refleje el modo activo
      const sp = new URLSearchParams();
      sp.set("mode", nextMode);
      startTransition(() => {
        router.replace(`/?${sp.toString()}#search`);
      });
    }
  }

  return (
    <form onSubmit={onSubmit} className="w-full">
      <div className="flex gap-2 mb-5 flex-wrap">
        <ModeButton
          active={mode === "semantic"}
          onClick={() => onModeChange("semantic")}
          label="Equivalente"
        />
        <ModeButton
          active={mode === "complete"}
          onClick={() => onModeChange("complete")}
          label="Completar"
        />
      </div>

      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          name="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={PLACEHOLDERS[mode]}
          autoFocus
          className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-4 md:py-5 pr-28 md:pr-36 font-serif italic text-xl md:text-[28px] text-ink placeholder:text-ink-faint transition-colors"
        />
        <button
          type="submit"
          data-cursor="hover"
          disabled={!query.trim()}
          className="absolute right-0 top-1/2 -translate-y-1/2 border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-accent font-mono text-[10px] tracking-[3px] uppercase px-3.5 py-2.5 md:px-4 md:py-3 transition-colors flex items-center gap-2"
        >
          {isPending && (
            <span className="inline-block w-3 h-3 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
          )}
          {isPending ? "buscando" : "buscar"}
        </button>
      </div>
    </form>
  );
}

function ModeButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-cursor="hover"
      className={`font-mono text-[10px] tracking-[2.5px] uppercase px-3 py-1.5 transition-colors ${
        active
          ? "text-accent border-b border-accent"
          : "text-ink-dim hover:text-ink border-b border-transparent"
      }`}
    >
      {label}
    </button>
  );
}
