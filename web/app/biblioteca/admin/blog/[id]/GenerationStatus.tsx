"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

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
    title = "pendiente de aprobar";
    body =
      "El borrador (cuerpo, foto y enlazado) se genera automáticamente al " +
      "aprobar la propuesta. Apruébala y el texto aparecerá aquí.";
  } else if (generating) {
    title = "generando borrador…";
    body =
      "El borrador no quedó al aprobar (o estás esperando el reintento). El " +
      "cron lo regenera cada pocos minutos con investigación del corpus (RAG). " +
      "Esta página se actualiza sola; no hace falta que hagas nada.";
  } else if (kind === "news") {
    title = "noticia sin texto";
    body =
      "Las noticias traen su texto reescrito del agregador, no se generan con " +
      "RAG. Esta no tiene cuerpo (probablemente una entrada de prueba o un " +
      "fallo del scraper).";
  } else {
    title = "sin cuerpo";
    body =
      "Esta propuesta no tiene texto y no se pudo generar. Revisa el cron " +
      "generate_approved_drafts o vuelve a aprobarla.";
  }

  return (
    <div className="border border-divider p-5">
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-accent mb-2 flex items-center gap-2">
        {generating && (
          <span className="inline-block w-2 h-2 rounded-full bg-accent animate-pulse" />
        )}
        {title}
      </p>
      <p className="font-serif italic text-ink-dim leading-relaxed">{body}</p>
    </div>
  );
}
