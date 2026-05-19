import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Breadcrumbs from "@/components/Breadcrumbs";
import MarkdownArticle from "@/components/MarkdownArticle";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import type { PublicPostDetail } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 600;

const KIND_LABEL: Record<string, string> = {
  editorial: "Editorial",
  news: "Noticia",
  anniversary: "Efeméride",
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const p = await apiFetch<PublicPostDetail>(`/public/posts/${slug}`, {
      authenticated: false,
    });
    return {
      title: p.meta_title || `${p.title} · Entre Interiores`,
      description: p.meta_description || p.excerpt || undefined,
      alternates: { canonical: `${SITE_URL}/blog/${p.slug}` },
      openGraph: {
        type: "article",
        title: p.title,
        description: p.excerpt || undefined,
        url: `${SITE_URL}/blog/${p.slug}`,
        publishedTime: p.published_at,
        images: p.hero_image_url ? [p.hero_image_url] : undefined,
      },
    };
  } catch {
    return {};
  }
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let post: PublicPostDetail;
  try {
    post = await apiFetch<PublicPostDetail>(`/public/posts/${slug}`, {
      authenticated: false,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const articleJsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.title,
    description: post.excerpt ?? undefined,
    datePublished: post.published_at,
    image: post.hero_image_url ?? undefined,
    url: `${SITE_URL}/blog/${post.slug}`,
    isPartOf: { "@type": "Blog", url: `${SITE_URL}/blog`, name: "Diario · Entre Interiores" },
    author: { "@id": "https://davidruizsanchez.es/#person" },
    publisher: { "@id": "https://davidruizsanchez.es/#person" },
    mainEntityOfPage: { "@type": "WebPage", "@id": `${SITE_URL}/blog/${post.slug}` },
  };

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[800px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "De manera urgente", href: "/blog" },
            { label: post.title, href: `/blog/${post.slug}` },
          ]}
        />

        <article>
          <header className="mb-10">
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
              {KIND_LABEL[post.kind] || post.kind} · {formatDate(post.published_at)}
            </p>
            <h1 className="font-serif text-4xl md:text-[56px] text-ink leading-[0.95] tracking-[-1.5px] m-0">
              {post.title}
            </h1>
            {post.excerpt && (
              <p className="mt-5 font-serif italic text-xl text-ink-dim leading-relaxed">
                {post.excerpt}
              </p>
            )}
          </header>

          {post.hero_image_url && (
            <figure className="mb-10 -mx-5 md:mx-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={post.hero_image_url}
                alt={post.title}
                className="w-full h-auto max-h-[60vh] object-cover"
                loading="eager"
              />
            </figure>
          )}

          <MarkdownArticle markdown={post.body_md} />

          {post.source_url && post.source_name && (
            <p className="mt-12 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
              Fuente:{" "}
              <a
                href={post.source_url}
                target="_blank"
                rel="noopener noreferrer"
                data-cursor="hover"
                className="text-accent hover:underline"
              >
                {post.source_name} ↗
              </a>
            </p>
          )}
        </article>

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(articleJsonLd) }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
