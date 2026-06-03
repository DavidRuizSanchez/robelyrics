"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

// Crea una lista manual vacía y refresca la página para que aparezca.
export default function CreatePlaylist() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const n = name.trim();
    if (!n || busy) return;
    setBusy(true);
    try {
      await fetch("/biblioteca/listas/api", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: n }),
      });
      setName("");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={create} className="flex flex-col sm:flex-row gap-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Nombre de la lista nueva"
        maxLength={120}
        className="flex-1 bg-bg border border-divider rounded-sm px-4 py-2.5 font-serif text-ink placeholder:text-ink-faint focus:border-accent outline-none"
      />
      <button
        type="submit"
        disabled={busy || name.trim().length === 0}
        data-cursor="hover"
        className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 font-mono text-[11px] tracking-[2.5px] uppercase px-6 py-2.5 transition-colors rounded-sm"
      >
        crear lista
      </button>
    </form>
  );
}
