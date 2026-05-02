import Link from "next/link";
import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";

// Landing pública placeholder. En F.5 se rediseña con grid de discos + intro
// editorial + CTA al registro. De momento tiene lo mínimo para que el dominio
// no devuelva 404 si lo visita un crawler.

export const metadata = {
  title: "Entre Interiores · Cancionero de Robe Iniesta y Extremoduro",
  description:
    "Disco a disco, canción a canción: el universo de Robe Iniesta y Extremoduro contado por sus letras y por la comunidad de fans.",
};

export default function PublicLandingPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-16">
      <div className="mb-12 text-center">
        <LogoSunCloud
          name="Entre Interiores"
          color={T.ink}
          scale={1.1}
          stack
        />
      </div>

      <div className="max-w-2xl text-center space-y-6">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
          un cancionero íntimo
        </p>
        <h1 className="font-serif text-3xl md:text-5xl text-ink leading-[1.1] tracking-[-0.5px]">
          Robe Iniesta y Extremoduro,<br />
          <span className="italic text-ink-dim">verso a verso</span>
        </h1>
        <p className="font-serif italic text-ink-dim text-lg md:text-xl leading-relaxed max-w-xl mx-auto">
          La capa pública con catálogo, contexto y análisis de cada canción está en
          construcción. Mientras tanto, si ya tienes acceso al cancionero íntimo:
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-4">
          <Link
            href="/registro"
            data-cursor="hover"
            className="border border-accent bg-accent text-white hover:bg-accent-bright font-mono text-[11px] tracking-[3px] uppercase px-7 py-3.5 transition-colors"
          >
            crear cuenta
          </Link>
          <Link
            href="/login"
            data-cursor="hover"
            className="border border-divider text-ink-dim hover:border-accent hover:text-accent font-mono text-[11px] tracking-[3px] uppercase px-7 py-3.5 transition-colors"
          >
            entrar
          </Link>
        </div>
      </div>

      <footer className="mt-20 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint text-center">
        sitio fan no oficial · letras © sus autores
      </footer>
    </main>
  );
}
