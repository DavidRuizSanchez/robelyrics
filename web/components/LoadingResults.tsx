// Skeleton mostrado mientras se cargan los resultados.
export default function LoadingResults({ query }: { query: string }) {
  return (
    <section className="mt-14 space-y-6">
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-accent animate-pulse" />
        Buscando «{query}»…
        <span className="text-ink-faint normal-case tracking-normal">
          (semantic puede tardar 5-15s por el reranker LLM)
        </span>
      </p>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="border-b border-divider pb-8 animate-pulse"
          style={{ animationDelay: `${i * 100}ms` }}
        >
          <div className="h-7 bg-divider rounded w-3/4 mb-3" />
          <div className="h-4 bg-divider rounded w-1/2 mb-2" />
          <div className="h-3 bg-divider rounded w-2/3" />
        </div>
      ))}
    </section>
  );
}
