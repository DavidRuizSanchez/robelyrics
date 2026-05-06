import Link from "next/link";
import RotatingLine from "@/components/RotatingLine";
import Watermark from "@/components/Watermark";

export default function Hero() {
  return (
    <section className="relative px-5 md:px-14 py-16 md:py-28 max-w-[1100px] mx-auto">
      <Watermark
        text="entre interiores"
        size="70vw"
        rotate={-2}
        bottom="-15%"
        right="-15%"
        opacity={0.022}
      />

      <div className="flex items-center gap-3.5 mb-6 relative z-10">
        <span className="block w-7 h-px bg-accent" />
        <span className="font-mono text-[11px] tracking-[4px] uppercase text-accent">
          un cancionero íntimo
        </span>
      </div>

      <h1 className="relative z-10 font-serif text-5xl md:text-[92px] font-normal leading-[1.02] tracking-tight md:tracking-[-2.5px] m-0 text-ink">
        El universo de{" "}
        <em className="text-accent not-italic md:italic">Robe</em>
        <br />e <em className="text-accent not-italic md:italic">Extremoduro</em>,
        <br />
        verso a verso.
      </h1>

      <p className="relative z-10 font-serif italic text-base md:text-xl text-ink-dim mt-6 max-w-[580px] leading-relaxed">
        Un buscador para los que viven con sus letras dentro. Encuentra,
        completa, navega — y entra entre los versos.
      </p>

      <div className="relative z-10 mt-8 flex gap-3.5 flex-wrap">
        <Link
          href="/biblioteca?mode=semantic#search"
          data-cursor="hover"
          className="bg-accent hover:bg-accent-bright text-white font-mono text-[11px] tracking-[3px] uppercase px-5 py-3.5 transition-colors"
        >
          empezar a buscar
        </Link>
        <Link
          href="#disco-anchor"
          data-cursor="hover"
          className="border border-divider hover:border-divider-strong text-ink-dim hover:text-ink font-mono text-[11px] tracking-[3px] uppercase px-5 py-3.5 transition-colors"
        >
          ver discografía
        </Link>
      </div>

      <div className="relative z-10 mt-14 md:mt-20 pt-8 border-t border-divider min-h-[110px]">
        <span className="block font-mono text-[9px] tracking-[3px] uppercase text-ink-faint mb-3.5">
          [verso al azar]
        </span>
        <RotatingLine />
      </div>
    </section>
  );
}
