import { Suspense } from "react";
import SearchBox from "@/components/SearchBox";
import SearchResults from "@/components/SearchResults";
import LoadingResults from "@/components/LoadingResults";

type Mode = "semantic" | "complete";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; mode?: string }>;
}) {
  const sp = await searchParams;
  const query = (sp.q || "").trim();
  const mode: Mode = sp.mode === "complete" ? "complete" : "semantic";

  return (
    <main className="min-h-screen px-6 py-12">
      <header className="text-center mb-12">
        <h1 className="font-serif text-5xl md:text-6xl font-bold tracking-tight">
          RobeLyrics
        </h1>
        <p className="text-zinc-500 mt-2">
          El universo Extremoduro / Robe Iniesta, en una caja de búsqueda.
        </p>
      </header>

      <SearchBox initialQuery={query} initialMode={mode} />

      {query && (
        // El `key` fuerza a Suspense a remount con cada query/mode → loading state inmediato.
        <Suspense
          key={`${mode}:${query}`}
          fallback={<LoadingResults query={query} />}
        >
          <SearchResults query={query} mode={mode} />
        </Suspense>
      )}

      {!query && (
        <section className="max-w-3xl mx-auto mt-12 text-center">
          <p className="text-zinc-500 text-sm">
            Prueba algo como{" "}
            <span className="text-zinc-300 font-mono">«se acabó lo bonito»</span>{" "}
            en modo equivalente, o{" "}
            <span className="text-zinc-300 font-mono">«abre la puerta»</span>{" "}
            en completar.
          </p>
        </section>
      )}
    </main>
  );
}
