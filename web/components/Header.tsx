import Link from "next/link";

export default function Header() {
  return (
    <header className="border-b border-zinc-900 bg-zinc-950/80 backdrop-blur sticky top-0 z-10">
      <nav className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between text-sm">
        <Link
          href="/"
          className="font-serif font-bold text-zinc-100 hover:text-white"
        >
          RobeLyrics
        </Link>
        <div className="flex items-center gap-5 text-zinc-400">
          <Link href="/extremoduro" className="hover:text-zinc-100">
            Extremoduro
          </Link>
          <Link href="/robe" className="hover:text-zinc-100">
            Robe
          </Link>
          <form action="/logout" method="post" className="inline">
            <button
              type="submit"
              className="hover:text-zinc-100 text-zinc-500"
              title="Cerrar sesión"
            >
              salir
            </button>
          </form>
        </div>
      </nav>
    </header>
  );
}
