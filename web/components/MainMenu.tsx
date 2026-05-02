import Link from "next/link";

const ITEMS = [
  {
    n: "01",
    title: "Equivalente poético",
    desc: "Cuéntame cómo te sientes y te doy la letra que lo dice.",
    example: '"se acabó lo bonito" → "se acabaron las flores de papel"',
    href: "/?mode=semantic#search",
  },
  {
    n: "02",
    title: "Completa la frase",
    desc: "Empieza una línea y descubre cómo continúa en el cancionero.",
    example: '"abre la puerta" → "que soy el diablo…"',
    href: "/?mode=complete#search",
  },
  {
    n: "03",
    title: "Discos y canciones",
    desc: "Navega el catálogo entero. Cada disco, cada letra, cada año.",
    example: "15 discos · 144 canciones",
    href: "/discografia",
  },
];

export default function MainMenu() {
  return (
    <section className="px-5 md:px-14 pb-16 md:pb-20 max-w-[1100px] mx-auto">
      <div className="flex flex-col border-t border-divider">
        {ITEMS.map((it) => (
          <Link
            key={it.n}
            href={it.href}
            data-cursor="hover"
            className="group grid grid-cols-[auto_1fr_auto] md:grid-cols-[80px_1fr_auto] gap-4 md:gap-8 items-center py-7 md:py-10 border-b border-divider transition-[padding] duration-200 ease-[cubic-bezier(.2,.8,.2,1)] hover:pl-2.5 md:hover:pl-5"
          >
            <span className="font-mono text-[11px] md:text-[13px] tracking-[2px] text-accent self-start pt-2">
              {it.n}
            </span>
            <div>
              <h3 className="font-serif text-[26px] md:text-[38px] font-normal m-0 text-ink leading-[1.1] tracking-[-0.5px] transition-colors duration-200 group-hover:text-accent">
                {it.title}
              </h3>
              <p className="font-serif italic text-ink-dim mt-2 text-[15px] md:text-[17px] leading-[1.5] max-w-[520px]">
                {it.desc}
              </p>
              <p className="font-mono text-[10px] tracking-[1.5px] text-ink-faint mt-2.5 md:mt-3">
                {it.example}
              </p>
            </div>
            <span className="font-serif italic text-[28px] md:text-[36px] text-ink-dim self-start pt-1 transition-all duration-200 ease-[cubic-bezier(.2,.8,.2,1)] group-hover:text-accent group-hover:translate-x-2">
              →
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
