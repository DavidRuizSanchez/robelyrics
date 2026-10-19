import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import EditorForm from "./EditorForm";

type SeoOut = {
  id: number;
  entity_type: string;
  entity_id: number;
  slug: string;
  entity_label: string;
  body_md: string;
  meta_title: string | null;
  meta_description: string | null;
  h1: string | null;
  schema_jsonld: Record<string, unknown> | null;
  generated_at: string;
  generated_by: string;
  reviewed_at: string | null;
  published: boolean;
  public_url: string;
  resolved_title: string;
  resolved_description: string;
  resolved_h1: string;
};

export const metadata = {
  title: "Editor SEO · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function EditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect(`/login?from=/biblioteca/admin/seo/${id}`);
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let detail: SeoOut;
  try {
    detail = await apiFetch<SeoOut>(`/admin/seo/${id}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="px-5 md:px-14 py-8 md:py-10 max-w-[1100px] mx-auto">
      <Link href="/biblioteca/admin/seo" className="text-sm text-ink-dim hover:text-ink">
        ← Volver a las fichas
      </Link>

      <header className="mt-6 mb-2">
        <p className="text-sm text-ink-dim mb-1">Ficha SEO · {detail.entity_type}</p>
        <h1 className="font-serif text-3xl md:text-4xl text-ink leading-[1.15]">{detail.entity_label}</h1>
        <p className="text-sm text-ink-faint mt-2">
          Generada por <span className="font-mono">{detail.generated_by}</span> el{" "}
          {new Date(detail.generated_at).toLocaleString("es-ES")} ·{" "}
          <Link href={detail.public_url} target="_blank" className="text-accent hover:underline">
            Ver en la web (si está publicada) ↗
          </Link>
        </p>
      </header>

      <EditorForm initial={detail} />
    </main>
  );
}
