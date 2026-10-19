// Kit del panel admin. Primitivas PRESENTACIONALES y sin hooks: sirven igual en
// server components (listas, usuarios, uso) que dentro de los planners cliente.
// Lo que necesita estado (el glosario) vive aparte, en Term.tsx.
//
// Reglas que encarnan (ver el plan del rediseño):
// - texto de interfaz en `font-ui`; el mono solo para DATOS (URLs, cifras, ids);
// - el estado siempre con texto, el color solo lo refuerza;
// - tres niveles de acción distinguibles por FORMA: primaria rellena,
//   secundaria con borde, peligrosa con borde + icono y separada.

import type { ReactNode } from "react";
import type { Tone } from "@/lib/admin/labels";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
  neutral: "text-ink-dim",
  accent: "text-accent",
};

const TONE_BADGE: Record<Tone, string> = {
  ok: "bg-ok-bg text-ok border-ok/30",
  warn: "bg-warn-bg text-warn border-warn/30",
  danger: "bg-danger-bg text-danger border-danger/30",
  info: "bg-info-bg text-info border-info/30",
  neutral: "bg-paper-hi text-ink-dim border-divider-strong",
  accent: "bg-accent/10 text-accent border-accent/40",
};

const TONE_STRIPE: Record<Tone, string> = {
  ok: "border-l-ok",
  warn: "border-l-warn",
  danger: "border-l-danger",
  info: "border-l-info",
  neutral: "border-l-divider-strong",
  accent: "border-l-accent",
};

export function toneText(tone: Tone): string {
  return TONE_TEXT[tone];
}

// ── Estructura ──────────────────────────────────────────────────────────────

/** Cabecera de cada pantalla: qué es y para qué sirve, en una frase. */
export function AdminPage({
  title,
  intro,
  actions,
  children,
}: {
  title: string;
  intro?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="px-5 md:px-14 py-8 md:py-10 max-w-[1100px] mx-auto">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          <h1 className="font-serif text-3xl md:text-4xl text-ink leading-tight">{title}</h1>
          {intro && <p className="mt-2 text-ink-dim">{intro}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </header>
      <div className="space-y-10">{children}</div>
    </main>
  );
}

/** Bloque con título, contador y una ayuda plegable de qué hay aquí. */
export function Section({
  id,
  title,
  count,
  help,
  actions,
  children,
}: {
  id?: string;
  title: string;
  count?: number | string;
  help?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-28">
      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-3">
        <h2 className="text-lg font-semibold text-ink">
          {title}
          {count !== undefined && (
            <span className="ml-2 font-mono text-sm font-normal text-ink-faint">{count}</span>
          )}
        </h2>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {help && <p className="-mt-1 mb-4 text-sm text-ink-faint max-w-2xl">{help}</p>}
      {children}
    </section>
  );
}

/** Tarjeta con franja lateral del tono de su estado. */
export function Card({
  tone = "neutral",
  className,
  children,
  as: Tag = "div",
}: {
  tone?: Tone;
  className?: string;
  children: ReactNode;
  as?: "div" | "li" | "article";
}) {
  return (
    <Tag
      className={cx(
        "bg-paper border border-divider border-l-4 rounded-md p-4 md:p-5",
        TONE_STRIPE[tone],
        className,
      )}
    >
      {children}
    </Tag>
  );
}

/** Etiqueta pequeña de sección dentro de una tarjeta («Qué propone el sistema»). */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cx("text-[11px] font-medium uppercase tracking-wider text-ink-faint", className)}>
      {children}
    </p>
  );
}

/** Detalle técnico plegado: lo que respalda una decisión, sin estorbar. */
export function Details({
  summary,
  children,
  className,
}: {
  summary: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details className={cx("group/det", className)}>
      <summary className="cursor-pointer list-none text-sm text-ink-dim hover:text-ink inline-flex items-center gap-1.5 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden">
        <span aria-hidden className="text-[10px] transition-transform group-open/det:rotate-90">
          ▶
        </span>
        {summary}
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

// ── Estado ──────────────────────────────────────────────────────────────────

export function StatusBadge({
  tone = "neutral",
  children,
  title,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONE_BADGE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Explicación o aviso en bloque. */
export function Callout({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role={tone === "danger" ? "alert" : undefined}
      className={cx("rounded-md border px-3 py-2 text-sm", TONE_BADGE[tone], className)}
    >
      {title && <p className="font-medium">{title}</p>}
      {children && <div className={cx("text-ink-dim", title ? "mt-0.5" : "")}>{children}</div>}
    </div>
  );
}

/** Resultado de una acción (sustituye a los alert()). Se anuncia a lectores de pantalla. */
export function Notice({
  tone = "danger",
  children,
  onClose,
}: {
  tone?: Tone;
  children: ReactNode;
  onClose?: () => void;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cx(
        "flex items-start justify-between gap-3 rounded-md border px-3 py-2 text-sm",
        TONE_BADGE[tone],
      )}
    >
      <div className="min-w-0 break-words">{children}</div>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar aviso"
          className="shrink-0 opacity-70 hover:opacity-100"
        >
          ✕
        </button>
      )}
    </div>
  );
}

/** Algo que está EN CURSO: nunca debe parecer un fallo. */
export function JobStatus({
  label,
  since,
  hint,
}: {
  label: ReactNode;
  since?: string | null;
  hint?: ReactNode;
}) {
  return (
    <div className="inline-flex flex-wrap items-center gap-2 rounded-md border border-info/30 bg-info-bg px-3 py-1.5 text-sm text-info">
      <span aria-hidden className="inline-block h-2 w-2 animate-pulse rounded-full bg-info" />
      <span className="font-medium">{label}</span>
      {since && <span className="text-ink-faint">desde {since}</span>}
      {hint && <span className="text-ink-dim">· {hint}</span>}
    </div>
  );
}

// ── Cifras ──────────────────────────────────────────────────────────────────

export function Metric({
  label,
  value,
  hint,
  tone = "neutral",
  href,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  href?: string;
}) {
  const body = (
    <>
      <p className="text-sm text-ink-dim">{label}</p>
      <p className={cx("mt-1 font-mono text-2xl", tone === "neutral" ? "text-ink" : TONE_TEXT[tone])}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>}
    </>
  );
  const cls = "block rounded-md border border-divider bg-paper px-4 py-3";
  return href ? (
    <a href={href} className={cx(cls, "hover:border-divider-strong hover:bg-paper-hi")}>
      {body}
    </a>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{children}</div>;
}

// ── Acciones ────────────────────────────────────────────────────────────────

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  // Texto oscuro sobre el granate: 5,3:1. El blanco de antes daba 3,7:1.
  primary:
    "bg-accent text-bg font-semibold border border-accent hover:bg-accent-bright hover:border-accent-bright",
  secondary: "border border-divider-strong text-ink hover:border-ink-dim hover:bg-paper-hi",
  ghost: "text-ink-dim hover:text-ink hover:bg-paper-hi",
  danger: "border border-danger/40 text-danger hover:bg-danger-bg",
};

export const focusRing =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export function buttonClass(variant: ButtonVariant = "secondary", size: "sm" | "md" = "md"): string {
  return cx(
    "inline-flex items-center justify-center gap-1.5 rounded-md transition-colors whitespace-nowrap disabled:opacity-40 disabled:pointer-events-none",
    size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm",
    BUTTON_VARIANT[variant],
    focusRing,
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  loadingLabel,
  className,
  children,
  type = "button",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  loading?: boolean;
  loadingLabel?: ReactNode;
}) {
  return (
    <button
      type={type}
      aria-busy={loading || undefined}
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(buttonClass(variant, size), className)}
    >
      {loading ? (loadingLabel ?? "…") : children}
    </button>
  );
}

/** Interruptor persistente (no una acción): enseña si está encendido. */
export function Toggle({
  pressed,
  onClick,
  disabled,
  children,
  title,
  tone = "danger",
}: {
  pressed: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
  title?: string;
  tone?: Tone;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cx(
        "inline-flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors disabled:opacity-40",
        focusRing,
        pressed ? TONE_BADGE[tone] + " border" : "text-ink-dim hover:text-ink hover:bg-paper-hi",
      )}
    >
      <span
        aria-hidden
        className={cx(
          "relative inline-block h-4 w-7 rounded-full transition-colors",
          pressed ? "bg-current" : "bg-divider-strong",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 h-3 w-3 rounded-full bg-bg transition-all",
            pressed ? "left-3.5" : "left-0.5",
          )}
        />
      </span>
      {children}
    </button>
  );
}

/**
 * Barra de acciones: la principal delante, las secundarias al lado y las
 * peligrosas separadas a la derecha, para que no se pulse una por otra.
 */
export function ActionBar({
  primary,
  secondary,
  danger,
  className,
}: {
  primary?: ReactNode;
  secondary?: ReactNode;
  danger?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 pt-4 mt-4 border-t border-divider",
        className,
      )}
    >
      {primary && <div className="flex flex-wrap gap-2">{primary}</div>}
      {secondary && <div className="flex flex-wrap items-center gap-1">{secondary}</div>}
      {danger && (
        <div className="flex flex-wrap items-center gap-2 sm:ml-auto sm:pl-4 sm:border-l sm:border-divider">
          {danger}
        </div>
      )}
    </div>
  );
}

// ── Formularios ─────────────────────────────────────────────────────────────

export const inputClass = cx(
  "w-full rounded-md border border-divider-strong bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-faint",
  "focus:border-accent",
  focusRing,
);

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink-dim">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

/** Pestañas de filtro como enlaces o botones con el mismo aspecto. */
export function filterClass(active: boolean): string {
  return cx(
    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors",
    focusRing,
    active
      ? "border-accent bg-accent/10 text-ink"
      : "border-divider text-ink-dim hover:border-divider-strong hover:text-ink",
  );
}

// ── Datos ───────────────────────────────────────────────────────────────────

/** Un dato (URL, keyword, id): mono, para distinguirlo del texto. */
export function Data({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[13px] text-ink", className)}>{children}</span>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-dashed border-divider-strong px-4 py-6 text-center text-ink-faint">
      {children}
    </p>
  );
}

/** Tabla sobria y legible; las cabeceras van en texto normal, no en mono uppercase. */
export function Table({
  head,
  children,
}: {
  head: ReactNode[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-divider">
      {/* Ancho mínimo: en móvil se desplaza dentro de su caja en vez de partir las URLs letra a letra. */}
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead className="bg-paper-hi text-ink-dim">
          <tr>
            {head.map((h, i) => (
              <th key={i} scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-divider">{children}</tbody>
      </table>
    </div>
  );
}

export const tdClass = "px-3 py-2 align-top";
