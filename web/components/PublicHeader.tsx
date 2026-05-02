import Link from "next/link";
import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";

export default function PublicHeader() {
  return (
    <header className="sticky top-0 z-40 flex items-center justify-between px-5 md:px-14 py-4 md:py-5 border-b border-divider bg-bg/90 backdrop-blur supports-[backdrop-filter]:bg-bg/70">
      <Link href="/" data-cursor="hover" className="block">
        <LogoSunCloud name="Entre Interiores" color={T.ink} scale={0.7} />
      </Link>

      <nav className="hidden md:flex items-center gap-7 font-mono text-[10px] tracking-[2.5px] uppercase">
        <Link
          href="/extremoduro"
          data-cursor="hover"
          className="text-ink-dim hover:text-ink transition-colors"
        >
          Extremoduro
        </Link>
        <Link
          href="/robe"
          data-cursor="hover"
          className="text-ink-dim hover:text-ink transition-colors"
        >
          Robe
        </Link>
        <Link
          href="/login"
          data-cursor="hover"
          className="border border-accent/60 text-accent hover:bg-accent hover:text-white px-4 py-2 transition-colors"
        >
          acceder
        </Link>
      </nav>
    </header>
  );
}
