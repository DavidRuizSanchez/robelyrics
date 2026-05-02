import Link from "next/link";
import { DolphinMark, LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";

export default function Footer() {
  return (
    <footer className="px-5 md:px-14 py-10 md:py-16 border-t border-divider max-w-[1100px] mx-auto">
      <div className="flex flex-col md:flex-row gap-8 md:gap-0 md:items-center md:justify-between">
        <div>
          <LogoSunCloud
            name="Entre Interiores"
            color={T.inkDim}
            scale={0.75}
          />
          <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-3.5">
            un cancionero íntimo · 2026
          </p>
        </div>
        <div className="flex gap-6 items-center">
          <DolphinMark size={50} color={T.inkFaint} />
          <DolphinMark size={36} color={T.inkFaint} />
        </div>
      </div>
      <div className="mt-8 pt-5 border-t border-divider flex flex-col md:flex-row md:justify-between gap-3 font-mono text-[10px] tracking-[2px] text-ink-faint uppercase">
        <span>No oficial · Letras © sus autores</span>
        <div className="flex gap-4">
          <Link href="/biblioteca" data-cursor="hover" className="hover:text-ink">
            Inicio
          </Link>
          <Link
            href="/biblioteca/discografia"
            data-cursor="hover"
            className="hover:text-ink"
          >
            Discografía
          </Link>
        </div>
      </div>
    </footer>
  );
}
