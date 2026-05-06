import Link from "next/link";

const PATREON_URL = "https://www.patreon.com/c/EntreInteriores";
const KOFI_URL = "https://ko-fi.com/entreinteriores";

export default function PatreonCTA() {
  return (
    <section className="px-5 md:px-14 py-20 md:py-28 max-w-[920px] mx-auto text-center border-t border-b border-divider">
      <div className="flex items-center justify-center gap-3.5 mb-6">
        <span className="block w-6 h-px bg-accent" />
        <span className="font-mono text-[11px] tracking-[4px] uppercase text-accent">
          una invitación
        </span>
        <span className="block w-6 h-px bg-accent" />
      </div>

      <h2 className="font-serif text-3xl md:text-5xl text-ink leading-[1.1] tracking-[-0.5px] mb-6">
        Si te acompaña,{" "}
        <em className="text-accent">apóyalo</em>
      </h2>

      <p className="font-serif italic text-ink-dim text-lg md:text-xl leading-relaxed max-w-2xl mx-auto mb-10">
        Este es mi pequeño homenaje a Robe, siempre me sentiré en deuda
        eterna con él por todo lo que me ha dado. <em>Entre Interiores</em>{" "}
        se sostiene a base de embeddings e insomnio. Si este proyecto te
        dice algo, aunque sea un poquito, ayuda a que siga creciendo,
        verso a verso, teniendo en cuenta tu voz.
      </p>

      <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 justify-center items-center">
        <Link
          href={PATREON_URL}
          target="_blank"
          rel="noopener noreferrer"
          data-cursor="hover"
          className="inline-block bg-accent hover:bg-accent-bright text-white font-mono text-[12px] tracking-[3px] uppercase px-9 py-4 transition-colors"
        >
          Hacerme mecenas en Patreon →
        </Link>
        <Link
          href={KOFI_URL}
          target="_blank"
          rel="noopener noreferrer"
          data-cursor="hover"
          className="inline-block border border-accent text-accent hover:bg-accent hover:text-white font-mono text-[12px] tracking-[3px] uppercase px-9 py-4 transition-colors"
        >
          Invitar a un café · Ko-fi →
        </Link>
      </div>

      <p className="mt-6 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
        patreon.com/c/EntreInteriores · ko-fi.com/entreinteriores
      </p>
    </section>
  );
}
