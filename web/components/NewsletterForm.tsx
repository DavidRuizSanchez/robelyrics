"use client";

import { type FormEvent, useState } from "react";

// Form de suscripción a la newsletter. POST al endpoint local del frontend
// que proxea al api. Mantenemos el estado en el cliente con feedback inline.

type State =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

type Variant = "footer" | "block";

export default function NewsletterForm({
  source,
  variant = "block",
}: {
  source: string;
  variant?: Variant;
}) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = email.trim().toLowerCase();
    if (!trimmed) return;
    setState({ kind: "submitting" });
    try {
      const res = await fetch("/api/newsletter/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: trimmed, source }),
      });
      const data = (await res.json()) as { status?: string; message?: string };
      if (!res.ok || data.status === "invalid_email") {
        setState({
          kind: "error",
          message: data.message || "No hemos podido apuntarte. Reintenta.",
        });
        return;
      }
      setState({
        kind: "success",
        message: data.message || "Te hemos enviado un email para confirmar.",
      });
      setEmail("");
    } catch {
      setState({ kind: "error", message: "Error de red. Reintenta en un momento." });
    }
  }

  const isFooter = variant === "footer";

  return (
    <form
      onSubmit={onSubmit}
      className={isFooter ? "" : "max-w-[560px] mx-auto"}
      aria-label="Suscripción a la newsletter"
    >
      {!isFooter && (
        <>
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
            de manera urgente · newsletter
          </p>
          <h3 className="font-serif text-2xl md:text-3xl text-ink leading-tight mb-3">
            Recibe las entradas nuevas en tu email
          </h3>
          <p className="font-serif italic text-ink-dim leading-relaxed mb-5">
            Sin más. Cuando se publique algo en el diario te llega un aviso.
            Doble confirmación, baja en un clic, cero spam.
          </p>
        </>
      )}

      <div className={isFooter ? "flex gap-2" : "flex flex-col sm:flex-row gap-2"}>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="tu@email.com"
          aria-label="Email para newsletter"
          className={
            isFooter
              ? "flex-1 min-w-0 px-3 py-2 bg-bg-deep border border-divider font-mono text-[11px] tracking-[1px] text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent"
              : "flex-1 px-4 py-3 bg-paper border border-divider font-serif text-base text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent"
          }
          disabled={state.kind === "submitting"}
        />
        <button
          type="submit"
          data-cursor="hover"
          disabled={state.kind === "submitting"}
          className={
            isFooter
              ? "px-3 py-2 border border-accent text-accent hover:bg-accent hover:text-white font-mono text-[10px] tracking-[2px] uppercase transition-colors disabled:opacity-40"
              : "px-5 py-3 bg-accent text-white hover:opacity-90 font-mono text-[11px] tracking-[2.5px] uppercase transition-opacity disabled:opacity-40"
          }
        >
          {state.kind === "submitting" ? "enviando…" : "apuntarme"}
        </button>
      </div>

      {state.kind === "success" && (
        <p
          className={
            isFooter
              ? "mt-2 font-mono text-[10px] tracking-[1px] text-accent"
              : "mt-3 font-serif italic text-accent"
          }
        >
          {state.message}
        </p>
      )}
      {state.kind === "error" && (
        <p
          className={
            isFooter
              ? "mt-2 font-mono text-[10px] tracking-[1px] text-ink-faint"
              : "mt-3 font-serif italic text-ink-faint"
          }
        >
          {state.message}
        </p>
      )}
    </form>
  );
}
