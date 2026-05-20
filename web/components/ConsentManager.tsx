"use client";

import Link from "next/link";
import Script from "next/script";
import { useEffect, useState } from "react";

const STORAGE_KEY = "entreinteriores-cookie-consent";
type Decision = "accepted" | "rejected";

/**
 * Gestiona el consentimiento de cookies (RGPD/ePrivacy) para Google Analytics.
 *
 * Comportamiento:
 *   - Si el usuario aún no ha decidido → muestra banner con botones
 *     Aceptar / Rechazar.
 *   - Si decidió "accepted" → carga GA4 (componente <GoogleAnalytics> de
 *     @next/third-parties).
 *   - Si decidió "rejected" → no carga GA4 ni guarda nada.
 *
 * La decisión se persiste en localStorage del navegador. Para
 * cambiar de opinión: limpiar el storage del sitio o esperar a que
 * añadamos un control en el footer (post-launch).
 */
export default function ConsentManager({ gaId }: { gaId: string }) {
  const [decision, setDecision] = useState<Decision | null | "loading">(
    "loading",
  );

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      setDecision(stored === "accepted" || stored === "rejected" ? stored : null);
    } catch {
      // Si localStorage no está disponible (modo privado raro), no
      // mostramos banner ni cargamos GA4 · fallback conservador.
      setDecision("rejected");
    }
  }, []);

  function decide(d: Decision) {
    try {
      window.localStorage.setItem(STORAGE_KEY, d);
    } catch {
      // ignoramos errores de localStorage
    }
    setDecision(d);
  }

  // Render condicional:
  // - "loading"           → null (evita flash de banner antes de hidratar)
  // - "accepted"          → carga GA4
  // - "rejected"          → nada
  // - null (sin decisión) → banner
  if (decision === "loading") return null;
  if (decision === "accepted") {
    return (
      <>
        <Script
          strategy="afterInteractive"
          src={`https://www.googletagmanager.com/gtag/js?id=${gaId}`}
        />
        <Script id="ga4-init" strategy="afterInteractive">
          {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${gaId}', { anonymize_ip: true });`}
        </Script>
      </>
    );
  }
  if (decision === "rejected") return null;

  return (
    <div
      role="dialog"
      aria-label="Aviso de cookies"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-divider bg-bg/95 backdrop-blur supports-[backdrop-filter]:bg-bg/85"
    >
      <div className="max-w-[1100px] mx-auto px-5 md:px-14 py-5 flex flex-col md:flex-row md:items-center gap-4 md:gap-8">
        <p className="font-serif italic text-ink-dim text-[14px] leading-relaxed flex-1">
          Usamos una cookie técnica esencial para mantener tu sesión y, si lo
          aceptas, Google Analytics anónimo para entender qué páginas
          funcionan. Más detalle en{" "}
          <Link
            href="/legal/cookies"
            data-cursor="hover"
            className="text-accent hover:underline"
          >
            política de cookies
          </Link>
          .
        </p>
        <div className="flex gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => decide("rejected")}
            data-cursor="hover"
            className="border border-divider hover:border-divider-strong text-ink-dim hover:text-ink font-mono text-[11px] tracking-[3px] uppercase px-5 py-3 transition-colors"
          >
            Rechazar
          </button>
          <button
            type="button"
            onClick={() => decide("accepted")}
            data-cursor="hover"
            className="border border-accent bg-accent text-white hover:bg-accent-bright font-mono text-[11px] tracking-[3px] uppercase px-5 py-3 transition-colors"
          >
            Aceptar
          </button>
        </div>
      </div>
    </div>
  );
}
