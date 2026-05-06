"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { resetPasswordAction } from "./actions";

export default function ResetForm({ token }: { token: string }) {
  const [mounted, setMounted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div
        className="w-full max-w-sm border border-divider bg-paper/30 p-8"
        style={{ height: 380 }}
        aria-hidden
      />
    );
  }

  async function onSubmit(formData: FormData) {
    setPending(true);
    setError(null);
    try {
      const res = await resetPasswordAction(formData);
      if (res && !res.ok) {
        setError(res.error);
      }
      // Si éxito, el server action redirige a /biblioteca y no volvemos.
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      action={onSubmit}
      className="w-full max-w-sm space-y-6 border border-divider bg-paper/30 p-8"
    >
      <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent text-center">
        nueva contraseña
      </p>
      <p className="font-serif italic text-ink-dim text-sm leading-relaxed text-center">
        Elige una contraseña nueva. Al guardar, todas tus sesiones activas
        en otros dispositivos se cerrarán por seguridad.
      </p>

      <input type="hidden" name="token" value={token} />

      <div>
        <label
          className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
          htmlFor="password"
        >
          Nueva contraseña
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif italic text-lg text-ink"
        />
      </div>

      <div>
        <label
          className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
          htmlFor="confirm"
        >
          Repítela
        </label>
        <input
          id="confirm"
          name="confirm"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif italic text-lg text-ink"
        />
      </div>

      {error && (
        <p className="text-accent text-sm font-mono tracking-[1px]">{error}</p>
      )}

      <button
        type="submit"
        disabled={pending}
        data-cursor="hover"
        className="w-full border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 disabled:cursor-wait font-mono text-[11px] tracking-[3px] uppercase py-3 transition-colors"
      >
        {pending ? "guardando…" : "guardar contraseña"}
      </button>

      <p className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint text-center">
        <Link href="/login" data-cursor="hover" className="text-accent hover:underline">
          ← volver al login
        </Link>
      </p>
    </form>
  );
}
