import type { Metadata } from "next";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { safeJsonLd } from "@/lib/safe-json-ld";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const metadata: Metadata = {
  title: "Quién ha hecho esto · Entre Interiores",
  description:
    "Quién hay detrás de Entre Interiores: un fan de Robe y Extremoduro desde los doce años. Una declaración de cariño escrita desde Madrid.",
  alternates: { canonical: `${SITE_URL}/sobre` },
};

const aboutJsonLd = {
  "@context": "https://schema.org",
  "@type": "AboutPage",
  url: `${SITE_URL}/sobre`,
  isPartOf: { "@type": "WebSite", url: SITE_URL, name: "Entre Interiores" },
  mainEntity: { "@id": "https://davidruizsanchez.es/#person" },
  about: { "@id": "https://davidruizsanchez.es/#person" },
};

export default function SobrePage() {
  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[760px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Quién ha hecho esto", href: "/sobre" },
          ]}
        />

        <header className="mb-10">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            quién hay detrás
          </p>
          <h1 className="font-serif text-5xl md:text-[64px] text-ink leading-[0.95] tracking-[-1.5px] m-0">
            Esto lo ha hecho un fan
          </h1>
          <p className="mt-6 font-serif italic text-xl text-ink-dim leading-relaxed">
            No hay agencia, no hay sello, no hay equipo. Hay un tío en Madrid
            que escucha a Robe desde hace muchos años y que un día decidió
            montar esto.
          </p>
        </header>

        <article className="font-serif text-lg md:text-[19px] text-ink leading-[1.7] space-y-6">
          <p>
            Me llamo{" "}
            <a
              href="https://davidruizsanchez.es"
              target="_blank"
              rel="noopener me author"
              data-cursor="hover"
              className="text-accent hover:underline"
            >
              David Ruiz Sánchez
            </a>{" "}
            y llevo desde los <strong>doce años</strong> con este señor
            metido en la oreja. Si echo cuentas, eso son ya más años de los
            que tienen muchos de los que se han metido en mi vida y se han
            ido. Por ahí pasó el punk, pasó el rock, pasó el techno, pasó
            la cumbia, pasaron etapas enteras en las que parecía que iba a
            cambiarme la vida la música electrónica de turno o el último
            disco que me pasaba un amigo. Pasaron todos. <strong>Robe se
            quedó.</strong>
          </p>

          <p>
            No es nostalgia adolescente. Lo he comprobado muchas veces:
            agarras cualquier disco de Extremoduro o de Robe a los doce, a
            los veinte, a los treinta y a los cuarenta y te dice cosas
            distintas cada vez, pero <em>te las dice a ti</em>. Hay versos
            que llevo grabados desde el instituto que han ido cambiando de
            significado con los años, defendiéndome de posiciones difíciles
            dentro de la propia cabeza, acompañándome en separaciones,
            entierros, mañanas de resaca y noches en las que no se podía
            estar solo de otra manera.
          </p>

          <p>
            Hay un punto en el que dejas de saber si Robe escribe sobre lo
            que vive él o sobre lo que vives tú. Para mí ese punto llegó
            pronto. Te juro que durante años he pensado en serio que muchas
            de esas canciones <strong>las estaba escribiendo para mí</strong>.
            Sé que es ridículo, pero también sé que cualquier fan suyo va a
            entender de qué hablo. La manera en que clava lo que sentimos los
            demás cuando ni siquiera nosotros sabíamos cómo nombrarlo es de
            las cosas más raras y más bonitas que se pueden encontrar en
            cualquier sitio. No solo en una canción.
          </p>

          <p>
            Esto que estás leyendo es lo que me ha salido de eso. Soy{" "}
            <em>SEO de profesión</em> (sí, exactamente lo que estás
            pensando), así que la combinación lógica era ponerme a hacer
            <strong> un sitio sobre Robe</strong>, llenarlo de letras
            comentadas con cariño, montar el buscador semántico que llevaba
            años deseando que existiera y empezar a contar todo lo que se me
            ocurriera contar sobre este universo. <em>Entre Interiores</em>{" "}
            es eso: el sitio que me hubiera gustado encontrar yo cuando
            tenía dieciséis años y todavía no había Internet de verdad.
          </p>

          <p>
            Aquí no se vende nada. No hay banners, no hay newsletter para
            colocarte cursos, no hay ningún plan de negocio. Hay <strong>un
            agradecimiento</strong>: en forma de letras explicadas, de
            buscador que entiende lo que quieres preguntar aunque no
            recuerdes el verso exacto, de pequeño diario donde voy dejando
            efemérides y noticias que merezca la pena contar, y de mucha
            música.
          </p>

          <p>
            Si te ha servido para algo, contento yo. Si te ha gustado,
            cuéntaselo a alguien. Si querías saber quién hay detrás:{" "}
            <em>pues yo, ya está</em>. Por si quieres ver lo que hago
            cuando no estoy montando sitios sobre Robe, mi web personal es{" "}
            <a
              href="https://davidruizsanchez.es"
              target="_blank"
              rel="noopener me author"
              data-cursor="hover"
              className="text-accent hover:underline"
            >
              davidruizsanchez.es
            </a>
            .
          </p>

          <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint pt-8 border-t border-divider">
            con cariño · desde madrid · siempre
          </p>
        </article>

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(aboutJsonLd) }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
