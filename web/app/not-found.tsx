import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Página no encontrada · Entre Interiores",
  robots: { index: false, follow: true },
};

// Página 404 estática (sin Header/Footer dinámicos) para que el build pueda
// prerenderizarla. La estética mínima imita la del site sin depender de
// componentes que requieren request context (cookies, fetch a /auth/me).
export default function NotFound() {
  return (
    <main
      style={{
        minHeight: "70vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "5rem 1.5rem",
        textAlign: "center",
      }}
    >
      <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-4">
        error 404
      </p>
      <h1 className="font-serif text-5xl md:text-[72px] text-ink leading-[0.95] tracking-[-1.5px] mb-6">
        Esa página no existe
      </h1>
      <p className="font-serif text-lg md:text-xl text-ink-dim leading-relaxed mb-10 max-w-[560px]">
        Puede que el enlace estuviera roto o que la canción se haya renombrado.
        Desde aquí puedes volver al inicio o explorar la discografía completa.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/"
          className="border border-accent text-accent hover:bg-accent hover:text-white px-5 py-3 font-mono text-[11px] tracking-[2.5px] uppercase transition-colors"
        >
          volver al inicio
        </Link>
        <Link
          href="/discografia"
          className="border border-divider text-ink-dim hover:text-ink hover:border-ink px-5 py-3 font-mono text-[11px] tracking-[2.5px] uppercase transition-colors"
        >
          ver discografía
        </Link>
        <Link
          href="/buscar"
          className="border border-divider text-ink-dim hover:text-ink hover:border-ink px-5 py-3 font-mono text-[11px] tracking-[2.5px] uppercase transition-colors"
        >
          buscar
        </Link>
      </div>
    </main>
  );
}
