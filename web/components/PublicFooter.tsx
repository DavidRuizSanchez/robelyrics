import Link from "next/link";
import NewsletterForm from "@/components/NewsletterForm";

// Discos destacados elegidos por relevancia editorial (los más icónicos del
// catálogo). Cada link aquí riega ~180 inlinks gratis a su destino, así que
// la selección importa: priorizamos hitos discográficos por encima de la
// completitud (la lista total vive en /discografia).
const FEATURED_ALBUMS: Array<{
  slug: string;
  title: string;
  artist: "extremoduro" | "robe";
  year: number;
}> = [
  { slug: "agila", title: "Agila", artist: "extremoduro", year: 1996 },
  { slug: "rock-transgresivo", title: "Rock Transgresivo", artist: "extremoduro", year: 1989 },
  { slug: "la-ley-innata", title: "La Ley Innata", artist: "extremoduro", year: 2008 },
  { slug: "iros-todos-a-tomar-por-culo", title: "Iros todos a tomar por culo", artist: "extremoduro", year: 1997 },
  { slug: "destrozares", title: "Destrozares", artist: "robe", year: 2018 },
  { slug: "mayeutica", title: "Mayéutica", artist: "robe", year: 2021 },
  { slug: "se-nos-lleva-el-aire", title: "Se nos lleva el aire", artist: "robe", year: 2024 },
];

const colTitleCls =
  "font-mono text-[10px] tracking-[3px] uppercase text-accent mb-4";
const linkCls =
  "block py-1 font-mono text-[11px] tracking-[1px] text-ink-dim hover:text-ink";

export default function PublicFooter() {
  return (
    <footer className="px-5 md:px-14 py-14 mt-20 border-t border-divider">
      <div className="max-w-[1100px] mx-auto grid grid-cols-2 md:grid-cols-4 gap-10 md:gap-8">
        {/* Col 1 — Artistas */}
        <div>
          <p className={colTitleCls}>Artistas</p>
          <Link href="/extremoduro" data-cursor="hover" className={linkCls}>
            Extremoduro
          </Link>
          <Link href="/robe" data-cursor="hover" className={linkCls}>
            Robe
          </Link>
          <Link href="/discografia" data-cursor="hover" className={linkCls}>
            Toda la discografía
          </Link>
        </div>

        {/* Col 2 — Discos destacados */}
        <div>
          <p className={colTitleCls}>Discos</p>
          {FEATURED_ALBUMS.map((a) => (
            <Link
              key={`${a.artist}-${a.slug}`}
              href={`/${a.artist}/${a.slug}`}
              data-cursor="hover"
              className={linkCls}
            >
              {a.title}{" "}
              <span className="text-ink-faint">({a.year})</span>
            </Link>
          ))}
        </div>

        {/* Col 3 — Explora */}
        <div>
          <p className={colTitleCls}>Explora</p>
          <Link
            href="/temas"
            data-cursor="hover"
            className={linkCls}
            title="Lo que aletea — temas que recorren el cancionero"
          >
            Lo que aletea
          </Link>
          <Link
            href="/lugares"
            data-cursor="hover"
            className={linkCls}
            title="Geografía emocional — lugares en las canciones"
          >
            Geografía
          </Link>
          <Link
            href="/conceptos"
            data-cursor="hover"
            className={linkCls}
            title="Bestiario — símbolos y figuras recurrentes"
          >
            Bestiario
          </Link>
          <Link
            href="/blog"
            data-cursor="hover"
            className={linkCls}
            title="De manera urgente — noticias y memoria"
          >
            De manera urgente
          </Link>
          <Link href="/buscar" data-cursor="hover" className={linkCls}>
            Buscar entre letras
          </Link>
        </div>

        {/* Col 4 — Sitio + legales */}
        <div>
          <p className={colTitleCls}>Sitio</p>
          <Link href="/legal/aviso" data-cursor="hover" className={linkCls}>
            Aviso legal
          </Link>
          <Link href="/legal/privacidad" data-cursor="hover" className={linkCls}>
            Privacidad
          </Link>
          <Link href="/legal/cookies" data-cursor="hover" className={linkCls}>
            Cookies
          </Link>
          <Link href="/legal/terminos" data-cursor="hover" className={linkCls}>
            Términos
          </Link>
          <Link href="/legal/takedown" data-cursor="hover" className={linkCls}>
            Takedown
          </Link>
          <Link href="/legal/atribuciones" data-cursor="hover" className={linkCls}>
            Atribuciones
          </Link>
          <Link href="/sobre" data-cursor="hover" className={linkCls}>
            Quién ha hecho esto
          </Link>
          <Link
            href="/login"
            data-cursor="hover"
            className="block py-1 font-mono text-[11px] tracking-[1px] text-accent hover:underline mt-2"
          >
            Acceder
          </Link>
        </div>
      </div>

      <div className="max-w-[1100px] mx-auto mt-12 pt-8 border-t border-divider/60 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-6 md:gap-12 items-start">
        <div>
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
            de manera urgente · newsletter
          </p>
          <p className="font-serif italic text-ink-dim text-[14px] leading-relaxed max-w-[420px]">
            Apúntate para que te avise cuando se publique algo en el diario.
            Sin spam, baja en un clic.
          </p>
        </div>
        <div className="md:w-[360px]">
          <NewsletterForm source="footer" variant="footer" />
        </div>
      </div>

      <div className="max-w-[1100px] mx-auto mt-8 pt-6 border-t border-divider/60 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
        © 2026 Entre Interiores · Sitio fan no oficial · Letras © sus autores
      </div>
    </footer>
  );
}
