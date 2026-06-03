import Link from "next/link";
import NewsletterForm from "@/components/NewsletterForm";
import InstagramLink from "@/components/InstagramLink";

const colTitleCls =
  "font-mono text-[10px] tracking-[3px] uppercase text-accent mb-4";
const linkCls =
  "block py-1 font-mono text-[11px] tracking-[1px] text-ink-dim hover:text-ink";

export default function PublicFooter() {
  return (
    <footer className="px-5 md:px-14 py-14 mt-20 border-t border-divider">
      <div className="max-w-[1100px] mx-auto grid grid-cols-2 md:grid-cols-3 gap-10 md:gap-8">
        {/* Col 1 · Universo Extremo (lo que cruza el cancionero) */}
        <div>
          <p className={colTitleCls}>Universo Extremo</p>
          <Link href="/temas" data-cursor="hover" className={linkCls} title="Temas que cruzan el cancionero">
            Lo que aletea
          </Link>
          <Link href="/lugares" data-cursor="hover" className={linkCls} title="La geografía de sus canciones">
            Geografía
          </Link>
          <Link href="/conceptos" data-cursor="hover" className={linkCls} title="Símbolos y bichos que se repiten">
            Bestiario
          </Link>
          <Link href="/discografia" data-cursor="hover" className={linkCls}>
            Toda la discografía
          </Link>
        </div>

        {/* Col 2 · Sitio + apoyar */}
        <div>
          <p className={colTitleCls}>El chiringuito</p>
          <Link href="/sobre" data-cursor="hover" className={linkCls}>
            Quién ha montado esto
          </Link>
          <Link
            href="/biblioteca/donar"
            data-cursor="hover"
            className="block py-1 font-mono text-[11px] tracking-[1px] text-accent hover:underline"
          >
            Echar una mano
          </Link>
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
          <Link href="/login" data-cursor="hover" className={linkCls}>
            Acceder
          </Link>
        </div>

        {/* Col 3 · Newsletter (en desktop como columna; en móvil baja entera) */}
        <div className="col-span-2 md:col-span-1" id="suscribete">
          <p className={colTitleCls}>De manera urgente</p>
          <p className="font-serif italic text-ink-dim text-[14px] leading-relaxed mb-4">
            Déjame el correo y te aviso cuando caiga algo nuevo en el diario.
            Ni spam ni rollos, te borras de un clic.
          </p>
          <NewsletterForm source="footer" variant="footer" />
        </div>
      </div>

      <div className="max-w-[1100px] mx-auto mt-12 pt-6 border-t border-divider/60 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
          © 2026 Entre Interiores · Sitio fan no oficial · Letras © sus autores
        </p>
        <InstagramLink
          showHandle
          className="text-ink-dim hover:text-accent transition-colors"
        />
      </div>
    </footer>
  );
}
