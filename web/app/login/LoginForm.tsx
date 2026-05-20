"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { loginAction } from "./actions";

/**
 * Form de login. Renderiza un placeholder vacío en el primer paint para evitar
 * hydration mismatches causados por extensiones como Keeper, 1Password,
 * LastPass, ColorZilla, etc., que inyectan elementos en los <input> y <form>
 * antes de que React hidrate.
 *
 * Cuando `mounted=false`, devolvemos un esqueleto con la misma altura para
 * evitar saltos de layout. Cuando se monta en cliente, el form aparece. Como
 * el form solo existe tras montar, no hay HTML servidor con el que comparar
 * y el mismatch desaparece.
 */
export default function LoginForm({
  from,
  error: initialError,
}: {
  from: string;
  error?: string;
}) {
  const [mounted, setMounted] = useState(false);
  const [error, setError] = useState<string | null>(initialError ?? null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    // Placeholder con la misma forma para que no haya layout shift al montar.
    return (
      <div
        className="w-full max-w-sm border border-divider bg-paper/30 p-8"
        style={{ height: 348 }}
        aria-hidden
      />
    );
  }

  // Wrapper local del server action: el form `action={fn}` requiere que `fn`
  // devuelva void/Promise<void> en Next 15. Aquí extraemos el `{error}` que
  // devuelve loginAction y lo plasmamos en estado local.
  async function onSubmit(formData: FormData) {
    setPending(true);
    setError(null);
    try {
      const res = await loginAction(formData);
      if (res && !res.ok) {
        setError(res.error);
      }
      // Si éxito, el server action redirige y no volvemos aquí.
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
        acceso privado
      </p>

      <input type="hidden" name="from" value={from} />

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

      <div>
        <label
          className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
          htmlFor="password"
        >
          Contraseña
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
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
        {pending ? "entrando…" : "entrar"}
      </button>

      <div className="space-y-1.5 text-center">
        <p className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint">
          <Link
            href="/olvide-password"
            data-cursor="hover"
            className="text-ink-dim hover:text-accent hover:underline"
          >
            ¿olvidaste tu contraseña?
          </Link>
        </p>
        <p className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint">
          ¿aún no tienes cuenta?{" "}
          <Link href="/registro" data-cursor="hover" className="text-accent hover:underline">
            crear cuenta
          </Link>
        </p>
      </div>
    </form>
  );
}
