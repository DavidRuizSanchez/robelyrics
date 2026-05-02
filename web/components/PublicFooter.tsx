import Link from "next/link";

export default function PublicFooter() {
  return (
    <footer className="px-5 md:px-14 py-12 mt-20 border-t border-divider">
      <div className="max-w-[1100px] mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
        <p>© 2026 Entre Interiores · Sitio fan no oficial · Letras © sus autores</p>
        <nav className="flex flex-wrap gap-x-4 gap-y-2">
          <Link href="/legal/aviso" data-cursor="hover" className="hover:text-accent">
            Aviso
          </Link>
          <Link href="/legal/privacidad" data-cursor="hover" className="hover:text-accent">
            Privacidad
          </Link>
          <Link href="/legal/cookies" data-cursor="hover" className="hover:text-accent">
            Cookies
          </Link>
          <Link href="/legal/terminos" data-cursor="hover" className="hover:text-accent">
            Términos
          </Link>
          <Link href="/legal/takedown" data-cursor="hover" className="hover:text-accent">
            Takedown
          </Link>
          <Link href="/login" data-cursor="hover" className="text-accent hover:underline">
            Acceder
          </Link>
        </nav>
      </div>
    </footer>
  );
}
