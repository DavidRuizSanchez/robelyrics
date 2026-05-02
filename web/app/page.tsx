import { Suspense } from "react";
import Link from "next/link";
import DiscographySection from "@/components/DiscographySection";
import Footer from "@/components/Footer";
import HeaderImageBackdrop from "@/components/HeaderImageBackdrop";
import Hero from "@/components/Hero";
import LoadingResults from "@/components/LoadingResults";
import MainMenu from "@/components/MainMenu";
import SearchBox from "@/components/SearchBox";
import SearchResults from "@/components/SearchResults";

type Mode = "semantic" | "complete";

const MODE_META: Record<Mode, { n: string; title: string }> = {
  semantic: { n: "01", title: "Equivalente poético" },
  complete: { n: "02", title: "Completa la frase" },
};

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; mode?: string }>;
}) {
  const sp = await searchParams;
  const query = (sp.q || "").trim();
  const mode: Mode | null =
    sp.mode === "semantic" || sp.mode === "complete" ? sp.mode : null;

  // Modo Experience (form + resultados)
  if (mode) {
    return (
      <Experience mode={mode} query={query} />
    );
  }

  // Home
  return (
    <div className="relative">
      <HeaderImageBackdrop height="1100px" />
      <div className="relative z-10">
        <Hero />
        <MainMenu />
        <DiscographySection variant="summary" />
        <Footer />
      </div>
    </div>
  );
}

function Experience({ mode, query }: { mode: Mode; query: string }) {
  const meta = MODE_META[mode];
  return (
    <main
      id="search"
      className="px-5 md:px-14 py-8 md:py-20 max-w-[920px] mx-auto animate-fade-up"
    >
      <Link
        href="/"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink transition-colors mb-7 inline-block"
      >
        ← volver
      </Link>

      <div className="flex items-center gap-3 mb-3.5">
        <span className="block w-6 h-px bg-accent" />
        <span className="font-mono text-[11px] tracking-[4px] uppercase text-accent">
          {meta.n}
        </span>
      </div>
      <h2 className="font-serif text-4xl md:text-[64px] font-normal text-ink m-0 leading-[1] tracking-[-1px]">
        {meta.title}
      </h2>

      <div className="mt-9">
        <SearchBox initialQuery={query} initialMode={mode} />
      </div>

      {query && (
        <Suspense
          key={`${mode}:${query}`}
          fallback={<LoadingResults query={query} />}
        >
          <SearchResults query={query} mode={mode} />
        </Suspense>
      )}

      {!query && (
        <p className="mt-6 font-mono text-[10px] tracking-[1px] text-ink-faint">
          {mode === "semantic"
            ? 'p.ej. «se acabó lo bonito»'
            : 'p.ej. «abre la puerta»'}
        </p>
      )}
    </main>
  );
}
