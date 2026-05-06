import Link from "next/link";
import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";
import { verifyTokenAction } from "./actions";

export const metadata = {
  title: "Verificar email · Entre Interiores",
  robots: { index: false, follow: false },
};

// El servidor ejecuta la verificación contra el API ANTES de renderizar.
// Si OK, ya hay cookie y mostramos confirmación + CTA "ir a la biblioteca".
// Si error, mostramos el motivo + CTA "volver al login".
export default async function VerifyEmailPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const state = await verifyTokenAction(token);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-10">
      <div className="mb-10">
        <LogoSunCloud
          name="Entre Interiores"
          color={T.ink}
          scale={1.1}
          stack
        />
      </div>

      <div className="w-full max-w-sm border border-divider bg-paper/30 p-8 space-y-5 text-center">
        {state.kind === "ok" ? (
          <>
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
              ✓ email verificado
            </p>
            <p className="font-serif text-lg text-ink leading-relaxed">
              Tu cuenta queda activada. Bienvenido al cancionero.
            </p>
            <Link
              href="/biblioteca"
              data-cursor="hover"
              className="inline-block w-full border border-accent bg-accent text-white hover:bg-accent-bright font-mono text-[11px] tracking-[3px] uppercase py-3 transition-colors"
            >
              entrar a la biblioteca →
            </Link>
          </>
        ) : (
          <>
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
              ✗ no se pudo verificar
            </p>
            <p className="font-serif italic text-ink-dim text-base leading-relaxed">
              {state.message}
            </p>
            <p className="font-serif italic text-ink-faint text-sm leading-relaxed">
              Si has clicado un correo antiguo, puede que tu cuenta ya esté
              activada. Prueba a entrar directamente con tu email y contraseña.
            </p>
            <Link
              href="/login"
              data-cursor="hover"
              className="inline-block w-full border border-accent bg-accent text-white hover:bg-accent-bright font-mono text-[11px] tracking-[3px] uppercase py-3 transition-colors"
            >
              ir al login
            </Link>
          </>
        )}
      </div>
    </main>
  );
}
