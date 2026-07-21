// Componente async aislado para que Suspense pueda mostrar el fallback
// mientras se hace el fetch al backend.

import SemanticResultCard from "@/components/SemanticResultCard";
import CompleteResultCard from "@/components/CompleteResultCard";
import { apiFetch, ApiError } from "@/lib/api";
import TrackEvent from "@/components/TrackEvent";
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
      <div className="mt-8 p-4 border border-accent/30 text-accent font-mono text-[12px] tracking-[1px]">
        {msg}
      </div>
    );
  }

  return (
    <section className="mt-14 space-y-9 animate-fade-up">
      <TrackEvent
        event={mode === "semantic" ? "buscador_semantico" : "completar"}
        params={{ n_results: result.results.length, query: query.slice(0, 100) }}
      />
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
        {result.results.length} resultado
        {result.results.length === 1 ? "" : "s"} para «{query}»
      </p>

      {result.results.length === 0 ? (
        <div className="border border-divider p-8 text-center text-ink-dim font-serif italic">
          Sin coincidencias. Prueba otra frase.
        </div>
      ) : mode === "semantic" ? (
        (result as SemanticOut).results.map((hit, i) => (
          <SemanticResultCard key={i} hit={hit} query={query} index={i} />
        ))
      ) : (
        (result as CompleteOut).results.map((hit, i) => (
          <CompleteResultCard key={i} hit={hit} query={query} />
        ))
      )}

      {mode === "semantic" &&
        ((result as SemanticOut).robe_says?.length ?? 0) > 0 && (
          <div className="mt-6 pt-8 border-t border-divider">
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-5">
              y esto dijo Robe
            </p>
            <div className="space-y-6">
              {(result as SemanticOut).robe_says!.map((r, i) => (
                <figure key={i} className="border-l-2 border-accent/40 pl-5">
                  <blockquote className="font-serif italic text-ink text-lg md:text-xl leading-relaxed m-0">
                    “{r.fragmento}”
                  </blockquote>
                  <figcaption className="mt-2 font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
                    {r.url ? (
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-cursor="hover"
                        className="hover:text-accent"
                      >
                        {r.titulo} ↗
                      </a>
                    ) : (
                      r.titulo
                    )}
                  </figcaption>
                </figure>
              ))}
            </div>
          </div>
        )}
    </section>
  );
}
