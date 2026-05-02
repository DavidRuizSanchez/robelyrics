"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";
import { registerAction, type RegisterResult } from "./actions";

// Mismo patrón "mounted" que LoginForm para evitar hydration mismatch con
// gestores de contraseñas (Keeper, 1Password, etc.).

export default function RegisterForm() {
  const [mounted, setMounted] = useState(false);
  const [result, setResult] = useState<RegisterResult | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div
        className="w-full max-w-sm border border-divider bg-paper/30 p-8"
        style={{ height: 540 }}
        aria-hidden
      />
    );
  }

  if (result?.ok) {
    return (
      <div className="w-full max-w-sm border border-accent/40 bg-paper/30 p-8 space-y-4">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent text-center">
          ✓ casi listo
        </p>
        <p className="font-serif text-lg text-ink leading-relaxed">
          Te hemos enviado un correo a <strong>{result.email}</strong>.
        </p>
        <p className="font-serif italic text-ink-dim text-base leading-relaxed">
          Pincha el enlace para confirmar tu email. Caduca en 24&nbsp;horas. Si
          no lo encuentras, mira en spam o en promociones.
        </p>
        {!result.emailSent && (
          <p className="font-mono text-[10px] tracking-[1.5px] text-ink-faint">
            (modo desarrollo · el envío real se activa con RESEND_API_KEY)
          </p>
        )}
        <Link
          href="/login"
          data-cursor="hover"
          className="block text-center font-mono text-[11px] tracking-[3px] uppercase text-accent hover:underline"
        >
          ir al login →
        </Link>
      </div>
    );
  }

  function onSubmit(formData: FormData) {
    startTransition(async () => {
      const r = await registerAction(formData);
      setResult(r);
    });
  }

  return (
    <form
      action={onSubmit}
      className="w-full max-w-sm space-y-5 border border-divider bg-paper/30 p-8"
    >
      <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent text-center">
        crear cuenta
      </p>

      <Field id="email" name="email" type="email" autoComplete="email" required label="Email" />
      <Field
        id="password"
        name="password"
        type="password"
        autoComplete="new-password"
        required
        label="Contraseña"
        hint="Mínimo 8 caracteres con letras y números"
      />
      <Field
        id="password_confirm"
        name="password_confirm"
        type="password"
        autoComplete="new-password"
        required
        label="Confirmar contraseña"
      />

      <label className="flex items-start gap-2.5 cursor-pointer">
        <input
          id="accept_terms"
          name="accept_terms"
          type="checkbox"
          required
          className="mt-1 accent-accent"
        />
        <span className="font-serif italic text-ink-dim text-[14px] leading-relaxed">
          Acepto los{" "}
          <Link href="/legal/terminos" target="_blank" className="text-accent underline">
            términos de uso
          </Link>{" "}
          y la{" "}
          <Link href="/legal/privacidad" target="_blank" className="text-accent underline">
            política de privacidad
          </Link>
          . Declaro que el acceso es para uso personal de estudio de la obra y
          que dispongo legítimamente de las grabaciones.
        </span>
      </label>

      {result && !result.ok && (
        <p className="text-accent text-sm font-mono tracking-[1px]">
          {result.error}
        </p>
      )}

      <button
        type="submit"
        disabled={isPending}
        data-cursor="hover"
        className="w-full border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 disabled:cursor-wait font-mono text-[11px] tracking-[3px] uppercase py-3 transition-colors"
      >
        {isPending ? "creando…" : "registrarme"}
      </button>

      <p className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint text-center">
        ¿ya tienes cuenta?{" "}
        <Link href="/login" data-cursor="hover" className="text-accent hover:underline">
          entrar
        </Link>
      </p>
    </form>
  );
}

function Field({
  id, name, type, autoComplete, required, label, hint,
}: {
  id: string;
  name: string;
  type: string;
  autoComplete: string;
  required?: boolean;
  label: string;
  hint?: string;
}) {
  return (
    <div>
      <label
        className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
        htmlFor={id}
      >
        {label}
      </label>
      <input
        id={id}
        name={name}
        type={type}
        autoComplete={autoComplete}
        required={required}
        className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif italic text-lg text-ink"
      />
      {hint && (
        <p className="text-ink-faint text-[10px] mt-1 font-mono tracking-[1px]">{hint}</p>
      )}
    </div>
  );
}
