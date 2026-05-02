// Skeleton mostrado mientras se cargan los resultados.
export default function LoadingResults({ query }: { query: string }) {
  return (
    <section className="max-w-3xl mx-auto mt-10 space-y-4">
      <p className="text-sm text-zinc-500 flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
        Buscando «{query}»…
        <span className="text-zinc-600 text-xs">
          (semantic puede tardar 5-15s por el reranker LLM)
        </span>
      </p>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 animate-pulse"
          style={{ animationDelay: `${i * 100}ms` }}
        >
          <div className="h-6 bg-zinc-800 rounded w-3/4 mb-3" />
          <div className="h-4 bg-zinc-800 rounded w-1/2 mb-2" />
          <div className="h-3 bg-zinc-800 rounded w-2/3" />
        </div>
      ))}
    </section>
  );
}
