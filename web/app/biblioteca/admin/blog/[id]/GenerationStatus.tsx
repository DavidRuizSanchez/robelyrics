"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Callout, JobStatus } from "@/components/admin/ui";

// Estado del borrador cuando la propuesta aún no tiene cuerpo. Si se está
// generando, refresca la página sola cada 5s hasta que aparezca el texto.
export default function GenerationStatus({
  status,
  kind,
}: {
  status: string;
  kind: string;
}) {
  const router = useRouter();

  const generable = ["spotlight", "evergreen", "anniversary", "album-anniversary"].includes(kind);
  const generating = generable && (status === "approved" || status === "scheduled");

  useEffect(() => {
    if (!generating) return;
    const t = setInterval(() => router.refresh(), 5000);
    return () => clearInterval(t);
  }, [generating, router]);

  let title: string;
  let body: string;
  if (status === "proposed") {
    title = "Pendiente de aprobar";
    body =
      "El borrador (cuerpo, foto y enlazado) se genera automáticamente al " +
      "aprobar la propuesta. Apruébala y el texto aparecerá aquí.";
  } else if (generating) {
    title = "Escribiendo el borrador…";
    body =
      "El borrador no quedó al aprobar (o estás esperando el reintento). El " +
      "cron lo regenera cada pocos minutos con investigación del corpus (RAG). " +
      "Esta página se actualiza sola; no hace falta que hagas nada.";
  } else if (kind === "news") {
    title = "Noticia sin texto";
    body =
      "Las noticias traen su texto reescrito del agregador, no se generan con " +
      "RAG. Esta no tiene cuerpo (probablemente una entrada de prueba o un " +
      "fallo del scraper).";
  } else {
    title = "Sin texto";
    body =
      "Esta propuesta no tiene texto y no se pudo generar. Revisa el cron " +
      "generate_approved_drafts o vuelve a aprobarla.";
  }

  if (generating) {
    return (
      <div className="space-y-2">
        <JobStatus label={title} hint="la página se actualiza sola" />
        <p className="text-ink-dim">{body}</p>
      </div>
    );
  }
  return (
    <Callout tone={status === "proposed" ? "info" : "warn"} title={title}>
      {body}
    </Callout>
  );
}
