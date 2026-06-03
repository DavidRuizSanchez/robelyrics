"use client";

import { useEffect, useRef, useState } from "react";

type PL = { id: number; name: string; track_count: number };

// Botón "+ Lista" en la ficha de canción: despliega las listas del usuario para
// añadir la canción actual, o crear una nueva al vuelo.
export default function AddToPlaylist({ songId }: { songId: number }) {
  const [open, setOpen] = useState(false);
  const [lists, setLists] = useState<PL[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  async function load() {
    try {
      const r = await fetch("/biblioteca/listas/api");
      if (r.ok) setLists((await r.json()) as PL[]);
      else setLists([]);
    } catch {
      setLists([]);
    }
  }

  useEffect(() => {
    if (open && lists === null) load();
  }, [open, lists]);

  // Cerrar al hacer clic fuera.
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  async function add(id: number, name: string) {
    if (busy) return;
    setBusy(true);
    try {
      const r = await fetch(`/biblioteca/listas/api/${id}/songs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ song_id: songId }),
      });
      if (r.ok) {
        setMsg(`Añadida a «${name}»`);
        setTimeout(() => {
          setOpen(false);
          setMsg(null);
        }, 1100);
      }
    } finally {
      setBusy(false);
    }
  }

  async function createAndAdd() {
    const n = newName.trim();
    if (!n || busy) return;
    setBusy(true);
    try {
      const r = await fetch("/biblioteca/listas/api", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: n }),
      });
      if (r.ok) {
        const pl = (await r.json()) as PL;
        setNewName("");
        await add(pl.id, pl.name);
        load();
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        type="button"
        data-cursor="hover"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 border border-accent/60 text-accent hover:bg-accent hover:text-white font-mono text-[10px] tracking-[2px] uppercase px-3 py-1.5 transition-colors rounded-sm"
      >
        <svg viewBox="0 0 16 16" className="w-3 h-3" fill="currentColor" aria-hidden>
          <path d="M7 2h2v5h5v2H9v5H7V9H2V7h5V2z" />
        </svg>
        Lista
      </button>

      {open && (
        <div className="absolute z-50 mt-2 w-64 bg-bg border border-divider rounded-sm shadow-xl right-0 p-2">
          {msg && (
            <p className="font-mono text-[10px] tracking-[1px] uppercase text-accent px-2 py-2">
              {msg}
            </p>
          )}
          {!msg && (
            <>
              <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint px-2 py-1.5">
                añadir a una lista
              </p>
              <div className="max-h-44 overflow-y-auto">
                {lists === null && (
                  <p className="px-2 py-2 font-serif italic text-ink-faint text-sm">
                    cargando…
                  </p>
                )}
                {lists && lists.length === 0 && (
                  <p className="px-2 py-2 font-serif italic text-ink-faint text-sm">
                    Aún no tienes listas. Crea una abajo.
                  </p>
                )}
                {lists?.map((pl) => (
                  <button
                    key={pl.id}
                    onClick={() => add(pl.id, pl.name)}
                    disabled={busy}
                    data-cursor="hover"
                    className="w-full text-left px-2 py-2 font-serif text-ink hover:text-accent hover:bg-paper transition-colors rounded-sm flex items-center justify-between gap-2"
                  >
                    <span className="truncate">{pl.name}</span>
                    <span className="font-mono text-[9px] text-ink-faint shrink-0">
                      {pl.track_count}
                    </span>
                  </button>
                ))}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  createAndAdd();
                }}
                className="flex gap-1 mt-2 pt-2 border-t border-divider"
              >
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Lista nueva…"
                  maxLength={120}
                  className="flex-1 min-w-0 bg-paper border border-divider rounded-sm px-2 py-1.5 text-sm font-serif text-ink placeholder:text-ink-faint focus:border-accent outline-none"
                />
                <button
                  type="submit"
                  disabled={busy || newName.trim().length === 0}
                  data-cursor="hover"
                  className="font-mono text-[9px] tracking-[1px] uppercase text-accent border border-accent/60 px-2 rounded-sm hover:bg-accent hover:text-white disabled:opacity-50 transition-colors"
                >
                  crear
                </button>
              </form>
            </>
          )}
        </div>
      )}
    </div>
  );
}
