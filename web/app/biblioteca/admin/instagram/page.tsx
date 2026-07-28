import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import InstagramPlanner from "./InstagramPlanner";

export type IGItem = {
  id: number;
  day: string;
  slot: number;
  position: number;
  status: string;
  content_type: string;
  /** IMAGE | CAROUSEL | REELS */
  media_type: string;
  /** Nº de piezas (diapositivas de un carrusel). */
  media_count: number;
  publish_on: string | null;
  /** Programación exacta (ISO, UTC). Si está, el item no entra en el goteo. */
  publish_at: string | null;
  title: string;
  category: string | null;
  summary: string | null;
  source_name: string | null;
  source_url: string | null;
  image_url: string | null;
  ig_media_id: string | null;
  error: string | null;
  is_blog: boolean;
  is_prepared: boolean;
  has_caption: boolean;
  created_at: string;
  published_at: string | null;
};

export type IGNewsCandidate = {
  id: number;
  title: string;
  category: string | null;
  source_medium: string | null;
  source_name: string;
  url: string;
  policy: string;
  relevance_score: number;
  published_at: string | null;
  fetched_at: string;
};

export type IGAccount = {
  ok: boolean;
  message: string;
  username: string | null;
};

export const metadata = {
  title: "Admin · Cola de Instagram · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function InstagramAdminPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/instagram");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  // El endpoint de cuenta llama a la Graph API; si las credenciales no están
  // configuradas devuelve ok=false con el mensaje. No tira la página.
  const [queue, candidates, account] = await Promise.all([
    apiFetch<IGItem[]>("/admin/instagram/queue?limit=200"),
    apiFetch<IGNewsCandidate[]>("/admin/instagram/news?limit=30"),
    apiFetch<IGAccount>("/admin/instagram/account").catch(
      () => ({ ok: false, message: "No se pudo consultar la cuenta", username: null }) as IGAccount,
    ),
  ]);

  return (
    <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
      <Link
        href="/biblioteca/admin/sources"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← admin
      </Link>

      <header className="mt-6 mb-10">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          panel admin
        </p>
        <h1 className="font-serif text-4xl md:text-5xl text-ink leading-[1.1] tracking-[-0.5px]">
          Cola de Instagram
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-3 max-w-2xl">
          Los posts que el sistema ha preparado para{" "}
          <span className="font-mono not-italic text-[12px] tracking-[1px] text-accent">
            @{account.username ?? "entreinterioresrobe"}
          </span>
          . Puedes encolar a mano, publicar ya o descartar.
        </p>

        <div
          className={`mt-5 inline-flex items-center gap-2 border px-3 py-2 ${
            account.ok
              ? "border-accent text-accent"
              : "border-divider text-ink-dim"
          }`}
        >
          <span className="font-mono text-[10px] tracking-[2px] uppercase">
            cuenta IG
          </span>
          <span className="font-mono text-[11px]">
            {account.ok
              ? `✓ ${account.username ?? "conectada"}`
              : `· ${account.message}`}
          </span>
        </div>
      </header>

      <InstagramPlanner
        queue={queue}
        candidates={candidates}
        account={account}
      />
    </main>
  );
}
