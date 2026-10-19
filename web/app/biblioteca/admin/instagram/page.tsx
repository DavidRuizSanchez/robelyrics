import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import InstagramPlanner from "./InstagramPlanner";
import ClipsPanel from "./ClipsPanel";
import { AdminPage, Callout, StatusBadge } from "@/components/admin/ui";

export type IGItem = {
  id: number;
  day: string;
  slot: number;
  position: number;
  status: string;
  content_type: string;
  /**
   * IMAGE | CAROUSEL | REELS | CLIP | PRODUCT.
   *
   * Los tres primeros son formas de contar un tema y los reparte
   * `scheduling.repartir_formatos`. CLIP (vídeo de otro canal) y PRODUCT (pieza
   * que enseña la web) NO: son un tema en sí, nacen con su propio post y el
   * repartidor no los toca.
   */
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
  /**
   * Pasó las guardas pero algo pide un par de ojos (la foto no se pudo
   * comprobar con visión, se silenció una entidad…). No se puede aprobar en
   * bloque: cada uno necesita su clic.
   */
  needs_human: boolean;
  /** ficha_propia | wikidata_p18 | google_images | arte_propio. */
  photo_source: string | null;
  /** Veredicto de la procedencia/identidad de esa foto. */
  photo_verdict: string | null;
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
    <AdminPage
      title="Instagram"
      intro={
        <>
          Lo que va a salir en{" "}
          <span className="font-mono text-ink">@{account.username ?? "entreinterioresrobe"}</span>:
          propuestas por aprobar, la cola que sale sola y los clips de vídeo.
        </>
      }
      actions={
        account.ok ? (
          <StatusBadge tone="ok">✓ Conectado a Instagram</StatusBadge>
        ) : (
          <StatusBadge tone="danger">✗ Sin conexión con Instagram</StatusBadge>
        )
      }
    >
      {!account.ok && (
        <Callout tone="danger" title="No se puede publicar ahora mismo">
          {account.message}. Mientras tanto se puede preparar y ordenar la cola, pero no publicar.
        </Callout>
      )}

      <InstagramPlanner queue={queue} candidates={candidates} account={account} />

      <ClipsPanel
        asignables={queue
          .filter((it) => it.status !== "published" && it.status !== "discarded")
          .map((it) => ({ id: it.id, title: it.title }))}
      />
    </AdminPage>
  );
}
