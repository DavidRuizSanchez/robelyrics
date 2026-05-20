import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import PostListWithActions from "./PostListWithActions";

type AdminPostItem = {
  id: number;
  slug: string;
  kind: string;
  status: string;
  title: string;
  excerpt: string | null;
  source_url: string | null;
  source_name: string | null;
  created_at: string;
  published_at: string | null;
};

export const metadata = {
  title: "Admin · Diario (posts) · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

const STATUSES = [
  { value: "all", label: "todos" },
  { value: "pending_review", label: "pendientes de revisar" },
  { value: "draft", label: "borrador" },
  { value: "approved", label: "aprobados (no publicados)" },
  { value: "published", label: "publicados" },
  { value: "rejected", label: "rechazados" },
];

export default async function AdminPostsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/posts");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  const { status = "pending_review" } = await searchParams;
  const items = await apiFetch<AdminPostItem[]>(`/admin/posts?status=${status}`);

  const counts = {
    total: items.length,
    pending: items.filter((i) => i.status === "pending_review").length,
    approved: items.filter((i) => i.status === "approved").length,
    published: items.filter((i) => i.status === "published").length,
  };

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
          Diario · revisión de entradas
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-3 max-w-2xl">
          Aprueba o rechaza las entradas detectadas por el scraper de noticias.
          Solo las publicadas se envían a los suscriptores en el próximo
          envío de newsletter.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8 text-center">
          <Stat label="en pantalla" value={counts.total} />
          <Stat label="pendientes" value={counts.pending} />
          <Stat label="aprobados" value={counts.approved} />
          <Stat label="publicados" value={counts.published} />
        </div>
      </header>

      <div className="flex flex-wrap gap-x-4 gap-y-2 mb-8 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint border-b border-divider pb-4">
        <span>filtro estado:</span>
        {STATUSES.map((s) => (
          <Link
            key={s.value}
            href={`/biblioteca/admin/posts?status=${s.value}`}
            data-cursor="hover"
            className={`hover:text-accent ${status === s.value ? "text-accent" : ""}`}
          >
            {s.label}
          </Link>
        ))}
      </div>

      <PostListWithActions items={items} />
    </main>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-divider py-4">
      <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
        {label}
      </p>
      <p className="font-serif text-3xl text-ink mt-1">{value}</p>
    </div>
  );
}
