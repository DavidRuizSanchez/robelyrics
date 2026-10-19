import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import PostEditor from "./PostEditor";
import { kindLabel } from "@/lib/admin/labels";

export type AdminPostDetail = {
  id: number;
  slug: string;
  kind: string;
  status: string;
  title: string;
  excerpt: string | null;
  body_md: string;
  meta_title: string | null;
  meta_description: string | null;
  hero_image_url: string | null;
  source_url: string | null;
  source_name: string | null;
  created_at: string;
  published_at: string | null;
  scheduled_for: string | null;
};

export const metadata = {
  title: "Admin · Editar entrada · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function EditPostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect(`/login?from=/biblioteca/admin/posts/${id}`);
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let post: AdminPostDetail;
  try {
    post = await apiFetch<AdminPostDetail>(`/admin/posts/${id}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="px-5 md:px-14 py-8 md:py-10 max-w-[900px] mx-auto">
      <Link href="/biblioteca/admin/blog" className="text-sm text-ink-dim hover:text-ink">
        ← Volver al blog
      </Link>

      <header className="mt-6 mb-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-dim">
        <span className="font-mono text-ink-faint">#{post.id}</span>
        <span>Entrada · {kindLabel(post.kind)}</span>
        <span className="font-mono text-ink-faint break-all">/blog/{post.slug}</span>
      </header>

      <PostEditor post={post} />
    </main>
  );
}
