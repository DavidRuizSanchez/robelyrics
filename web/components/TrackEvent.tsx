"use client";

import { useEffect } from "react";
import { trackFeature } from "@/lib/analytics";

// Dispara un evento GA4 al montar. Útil para features renderizadas en server
// components (p.ej. el buscador), donde no se puede llamar a gtag directamente.
export default function TrackEvent({
  event,
  params,
}: {
  event: string;
  params?: Record<string, string | number | boolean>;
}) {
  useEffect(() => {
    trackFeature(event, params);
    // solo al montar con estos valores
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event]);
  return null;
}
