import type { Metadata } from "next";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const metadata: Metadata = {
  title: "Confirmación de suscripción · Entre Interiores",
  description: "Confirmación de suscripción a la newsletter.",
  robots: { index: false, follow: false },
  alternates: { canonical: `${SITE_URL}/newsletter/confirmar` },
};

type StatusResponse = { status: string; message: string };

export default async function ConfirmarPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  let result: StatusResponse;
  if (!token) {
    result = { status: "invalid_token", message: "Falta el token de confirmación." };
  } else {
    try {
      result = await apiFetch<StatusResponse>(
        `/public/newsletter/confirm?token=${encodeURIComponent(token)}`,
        { authenticated: false },
      );
    } catch (e) {
      result = {
        status: "error",
        message:
          e instanceof ApiError
            ? "El enlace no es válido o ha caducado."
            : "Error inesperado. Reintenta más tarde.",
      };
    }
  }

  const isOk = result.status === "confirmed" || result.status === "already_confirmed";

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-14 md:py-20 max-w-[680px] mx-auto text-center">
        <Breadcrumbs
          className="mb-10 justify-center"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Confirmación", href: "/newsletter/confirmar" },
          ]}
        />

        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-4">
          newsletter · de manera urgente
        </p>
        <h1 className="font-serif text-4xl md:text-[56px] text-ink leading-[0.98] tracking-[-1px] mb-6">
          {isOk ? "Suscripción confirmada" : "Algo no cuadra"}
        </h1>
        <p className="font-serif italic text-xl text-ink-dim leading-relaxed mb-10">
          {result.message}
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/blog"
            data-cursor="hover"
            className="border border-accent text-accent hover:bg-accent hover:text-white px-5 py-3 font-mono text-[11px] tracking-[2.5px] uppercase transition-colors"
          >
            ir al diario
          </Link>
          <Link
            href="/"
            data-cursor="hover"
            className="border border-divider text-ink-dim hover:text-ink hover:border-ink px-5 py-3 font-mono text-[11px] tracking-[2.5px] uppercase transition-colors"
          >
            volver al inicio
          </Link>
        </div>
      </main>
      <PublicFooter />
    </>
  );
}
