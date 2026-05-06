import Link from "next/link";
import LogoBomba from "@/components/LogoBomba";

export const metadata = {
  title: "Apoyar Entre Interiores · Donaciones",
  robots: { index: false, follow: false },
};

export default function DonarPage() {
  return (
    <main className="px-5 md:px-14 py-12 md:py-20 max-w-3xl mx-auto">
      <div className="flex flex-col items-start gap-6 mb-8">
        <LogoBomba size={140} />
        <div className="flex items-center gap-3.5">
          <span className="block w-7 h-px bg-accent" />
          <span className="font-mono text-[11px] tracking-[4px] uppercase text-accent">
            una invitación
          </span>
        </div>
      </div>
      <h1 className="font-serif text-4xl md:text-[64px] text-ink leading-[0.97] tracking-[-1px] mb-6">
        Apoya <em className="text-accent">Entre Interiores</em>
      </h1>

      <p className="font-serif italic text-ink-dim text-lg md:text-xl leading-relaxed mb-10 max-w-2xl">
        Este es mi pequeño homenaje a Robe, siempre me sentiré en deuda eterna
        con él por todo lo que me ha dado. Entre Interiores se sostiene a base
        de embeddings e insomnio. Si este proyecto te dice algo, aunque sea un
        poquito, contribuye a que siga creciendo, verso a verso, teniendo en
        cuenta tu voz.
      </p>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8 mb-12">
        <article className="border border-divider p-7 flex flex-col">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            mecenazgo recurrente
          </p>
          <h2 className="font-serif text-2xl md:text-3xl text-ink leading-[1.1] mb-3">
            Patreon
          </h2>
          <p className="font-serif italic text-ink-dim text-base leading-relaxed flex-1 mb-6">
            Una contribución mensual, por pequeña que sea, hace que el sitio
            siga vivo y que pueda dedicarle tiempo a investigar, transcribir
            y escribir nuevos análisis. Tu nombre puede aparecer en{" "}
            <Link
              href="/legal/atribuciones"
              data-cursor="hover"
              className="text-accent hover:underline"
            >
              atribuciones
            </Link>{" "}
            si lo prefieres.
          </p>
          <Link
            href="https://www.patreon.com/c/EntreInteriores"
            target="_blank"
            rel="noopener noreferrer"
            data-cursor="hover"
            className="inline-block self-start border border-accent bg-accent text-white hover:bg-accent-bright font-mono text-[11px] tracking-[3px] uppercase px-7 py-3.5 transition-colors"
          >
            hacerme mecenas →
          </Link>
        </article>

        <article className="border border-divider p-7 flex flex-col">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            propina única
          </p>
          <h2 className="font-serif text-2xl md:text-3xl text-ink leading-[1.1] mb-3">
            Ko-fi
          </h2>
          <p className="font-serif italic text-ink-dim text-base leading-relaxed flex-1 mb-6">
            Si prefieres dejar una propina puntual sin compromiso, Ko-fi
            permite invitar a un café (o varios). Sin recurrencia, sin
            registro obligatorio, en menos de un minuto.
          </p>
          <Link
            href="https://ko-fi.com/entreinteriores"
            target="_blank"
            rel="noopener noreferrer"
            data-cursor="hover"
            className="inline-block self-start border border-accent text-accent hover:bg-accent hover:text-white font-mono text-[11px] tracking-[3px] uppercase px-7 py-3.5 transition-colors"
          >
            invitar a un café →
          </Link>
        </article>
      </section>

      <section className="border-t border-divider pt-8">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
          transparencia
        </p>
        <h3 className="font-serif text-xl text-ink mb-3">
          ¿En qué se gasta el dinero?
        </h3>
        <ul className="font-serif italic text-ink-dim leading-relaxed list-disc list-inside space-y-1">
          <li>Servidor Hetzner Cloud (~7€/mes).</li>
          <li>Dominio y CDN Cloudflare (~10€/año).</li>
          <li>API de OpenAI para embeddings y reranking (~5-15€/mes según uso).</li>
          <li>Tiempo: investigar fuentes, escribir análisis, mantener el catálogo al día.</li>
        </ul>
        <p className="font-serif italic text-ink-dim leading-relaxed mt-4">
          Cuando los gastos están cubiertos, el resto se reinvierte en mejorar
          el cancionero — más fuentes, mejor búsqueda, más canciones
          analizadas con cariño.
        </p>
      </section>
    </main>
  );
}
