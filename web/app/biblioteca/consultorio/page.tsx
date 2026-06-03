import type { Metadata } from "next";
import Breadcrumbs from "@/components/Breadcrumbs";
import { apiFetch } from "@/lib/api";
import ConsultorioChat from "./ConsultorioChat";

export const metadata: Metadata = {
  title: "Pregúntale al viento · Entre Interiores",
  robots: { index: false, follow: false },
};

const FALLBACK_SUGGESTIONS = [
  "¿Qué es para ti la libertad?",
  "¿En qué año salió Agila?",
  "¿Qué piensas de la fama?",
  "¿Qué es para ti la rabia?",
];

export default async function ConsultorioPage() {
  let suggestions: string[] = FALLBACK_SUGGESTIONS;
  try {
    suggestions = await apiFetch<string[]>("/consult/suggestions", {
      authenticated: false,
    });
  } catch {
    // usa el fallback
  }

  return (
    <main className="px-5 md:px-14 py-10 md:py-14 max-w-[860px] mx-auto">
      <Breadcrumbs
        className="mb-8"
        items={[
          { label: "Biblioteca", href: "/biblioteca" },
          { label: "Pregúntale al viento", href: "/biblioteca/consultorio" },
        ]}
      />

      <header className="mb-10">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          el viento responde
        </p>
        <h1 className="font-serif text-5xl md:text-[72px] text-ink leading-[0.95] tracking-[-2px] m-0">
          Pregúntale al viento
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-6 leading-relaxed">
          Pregunta al oráculo del Extremodurismo.
        </p>
      </header>

      <ConsultorioChat suggestions={suggestions} />

      <footer className="mt-16 pt-6 border-t border-divider">
        <p className="font-mono text-[10px] tracking-[1px] text-ink-faint leading-relaxed">
          Esto es un homenaje: una recreación de la voz de Robe construida a
          partir de material real (entrevistas, letras, su novela). No es Robe,
          ni habla por él ni por su familia. Cuando no hay nada suyo sobre algo,
          no se lo inventa.
        </p>
      </footer>
    </main>
  );
}
