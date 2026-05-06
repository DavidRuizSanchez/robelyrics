"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { forgotPasswordAction } from "./actions";

export default function ForgotForm() {
  const [mounted, setMounted] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div
        className="w-full max-w-sm border border-divider bg-paper/30 p-8"
        style={{ height: 280 }}
        aria-hidden
      />
    );
  }

  if (sent) {
    return (
      <div className="w-full max-w-sm space-y-5 border border-divider bg-paper/30 p-8 text-center">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
          comprueba tu bandeja
        </p>
        <p className="font-serif italic text-ink-dim leading-relaxed">
          Si <span className="text-ink not-italic">{sent}</span> tiene cuenta,
          en unos segundos te llega un email con un enlace para elegir una
          contraseña nueva. Caduca en 30 minutos.
        </p>
        <p className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint">
          <Link href="/login" data-cursor="hover" className="text-accent hover:underline">
            volver al login
          </Link>
        </p>
      </div>
    );
  }

  async function onSubmit(formData: FormData) {
    setPending(true);
    setError(null);
    try {
      const res = await forgotPasswordAction(formData);
      if (!res.ok) {
        setError(res.error);
        return;
      }
      setSent(res.email);
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
        recuperar contraseña
      </p>
      <p className="font-serif italic text-ink-dim text-sm leading-relaxed text-center">
        Te enviamos un enlace para elegir una nueva contraseña.
      </p>

      <div>
        <label
          className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
          htmlFor="email"
        >
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
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
        {pending ? "enviando…" : "enviar enlace"}
      </button>

      <p className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint text-center">
        <Link href="/login" data-cursor="hover" className="text-accent hover:underline">
          ← volver al login
        </Link>
      </p>
    </form>
  );
}
