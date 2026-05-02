// Componente async aislado para que Suspense pueda mostrar el fallback
// mientras se hace el fetch al backend.

import SemanticResultCard from "@/components/SemanticResultCard";
import CompleteResultCard from "@/components/CompleteResultCard";
import { apiFetch, ApiError } from "@/lib/api";
import type { SemanticOut, CompleteOut } from "@/lib/types";

type Mode = "semantic" | "complete";

export default async function SearchResults({
  query,
  mode,
}: {
  query: string;
  mode: Mode;
}) {
  let result: SemanticOut | CompleteOut;
  try {
    if (mode === "semantic") {
      result = await apiFetch<SemanticOut>("/search/semantic", {
        method: "POST",
        body: { query, k: 5 },
      });
    } else {
      result = await apiFetch<CompleteOut>("/search/complete", {
        method: "POST",
        body: { query, k: 3, n_continuation: 3 },
      });
    }
  } catch (e) {
    const msg =
      e instanceof ApiError ? `Error ${e.status}` : "Error inesperado";
    return (
      <div className="max-w-3xl mx-auto mt-8 p-4 bg-red-950/30 border border-red-900 rounded-lg text-red-300 text-sm">
        {msg}
      </div>
    );
  }

  return (
    <section className="max-w-3xl mx-auto mt-10 space-y-4">
      <p className="text-sm text-zinc-500">
        {result.results.length} resultado
        {result.results.length === 1 ? "" : "s"} para «{query}»
      </p>
      {result.results.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500">
          Sin coincidencias. Prueba otra frase.
        </div>
      ) : mode === "semantic" ? (
        (result as SemanticOut).results.map((hit, i) => (
          <SemanticResultCard key={i} hit={hit} query={query} />
        ))
      ) : (
        (result as CompleteOut).results.map((hit, i) => (
          <CompleteResultCard key={i} hit={hit} query={query} />
        ))
      )}
    </section>
  );
}
