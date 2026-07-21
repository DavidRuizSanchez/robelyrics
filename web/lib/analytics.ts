// Eventos GA4 de uso de features (F2.4). Solo dispara si gtag está cargado, y gtag
// solo se carga tras el consentimiento de cookies (ConsentManager) → respeta RGPD.
// NO se envía texto de consulta (PII): eso se registra server-side en la BD.

type GtagParams = Record<string, string | number | boolean | undefined>;

export function trackFeature(event: string, params?: GtagParams): void {
  if (typeof window === "undefined") return;
  const w = window as unknown as { gtag?: (...args: unknown[]) => void };
  if (typeof w.gtag === "function") {
    try {
      w.gtag("event", event, params || {});
    } catch {
      // nunca romper la feature por analytics
    }
  }
}
