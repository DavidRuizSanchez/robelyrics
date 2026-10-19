"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { GLOSARIO, type TerminoGlosario } from "@/lib/admin/labels";

/**
 * Término con explicación. Un `title=` no se ve en móvil ni con teclado, así
 * que es un botón que abre un globo: Enter/clic lo abre, Escape o salir lo cierra.
 */
export default function Term({
  k,
  children,
}: {
  k: TerminoGlosario;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-block">
      <button
        type="button"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((v) => !v)}
        className="underline decoration-dotted decoration-ink-faint underline-offset-4 hover:decoration-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent rounded-sm"
      >
        {children}
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute left-0 top-full z-30 mt-1 w-72 max-w-[80vw] rounded-md border border-divider-strong bg-paper-hi p-3 text-left text-sm font-normal normal-case tracking-normal text-ink-dim shadow-lg"
        >
          {GLOSARIO[k]}
        </span>
      )}
    </span>
  );
}
