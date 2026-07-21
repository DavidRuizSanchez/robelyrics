import type { Metadata } from "next";
import NextImage from "next/image";
import { notFound } from "next/navigation";
import Breadcrumbs from "@/components/Breadcrumbs";
import MarkdownArticle from "@/components/MarkdownArticle";
import PatreonCTA from "@/components/PatreonCTA";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  breadcrumbListNode,
  buildGraph,
  canonical,
  imageObjectNode,
  mentionsArray,
  postVideoObjectNode,
  webPageNode,
} from "@/lib/schema-graph";
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

  const mentions = mentionsArray(post.entities);
  const postPath = `/blog/${post.slug}`;
  // Imagen hero como ImageObject (con @id) para poder referenciarla desde el
  // Article y como primaryImageOfPage del WebPage.
  const heroImageNode = post.hero_image_url
    ? imageObjectNode({
        url: post.hero_image_url,
        path: postPath,
        attribution: post.hero_image_attribution,
      })
    : null;
  // Vídeos: la lista (posts premium con varios) o el único legacy.
  const videoList =
    post.videos && post.videos.length > 0
      ? post.videos
      : post.video
        ? [post.video]
        : [];
  // BlogPosting para editorial; NewsArticle para noticias/efemérides.
  const articleJsonLd: Record<string, unknown> = {
    "@type": post.kind === "editorial" ? "BlogPosting" : "NewsArticle",
    "@id": canonical.article(post.slug),
    headline: post.title,
    description: post.excerpt ?? undefined,
    datePublished: post.published_at,
    image: heroImageNode
      ? { "@id": canonical.primaryImage(postPath) }
      : undefined,
    url: `${SITE_URL}/blog/${post.slug}`,
    inLanguage: "es-ES",
    isPartOf: { "@id": canonical.blog },
    author: { "@id": "https://davidruizsanchez.es/#person" },
    publisher: { "@id": canonical.organization },
    mainEntityOfPage: { "@id": canonical.webPage(`/blog/${post.slug}`) },
  };
  if (mentions.length > 0) {
    articleJsonLd.mentions = mentions;
  }
  if (post.source_url) {
    articleJsonLd.isBasedOn = post.source_url;
  }

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
            <figure className="mb-10 -mx-5 md:mx-0 relative aspect-[16/9] max-h-[60vh] overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-restricted-imports */}
              <NextImage
                src={post.hero_image_url}
                alt={post.hero_image_alt || `Imagen relacionada: ${post.title}`}
                fill
                priority
                sizes="(max-width: 1100px) 100vw, 1100px"
                className="object-cover"
              />
              {post.hero_image_attribution && (
                <figcaption className="absolute bottom-0 right-0 bg-bg/75 backdrop-blur-sm px-2 py-1 font-mono text-[9px] tracking-[1px] text-ink-faint">
                  {post.hero_image_attribution.replace(/^\*|\*$/g, "")}
                </figcaption>
              )}
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
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                articleJsonLd,
                ...(heroImageNode ? [heroImageNode] : []),
                ...videoList
                  .filter((v) => v?.youtube_id)
                  .map((v) =>
                    postVideoObjectNode({
                      youtubeId: v.youtube_id,
                      title: v.title,
                      uploadDate: v.upload_date,
                      description: post.excerpt,
                      aboutId: canonical.article(post.slug),
                    }),
                  ),
                webPageNode({
                  path: postPath,
                  name: post.title,
                  mainEntityId: canonical.article(post.slug),
                  primaryImageId: heroImageNode
                    ? canonical.primaryImage(postPath)
                    : undefined,
                  datePublished: post.published_at,
                }),
                breadcrumbListNode(`/blog/${post.slug}`, [
                  { name: "Entre Interiores", item: "/" },
                  { name: "De manera urgente", item: "/blog" },
                  { name: post.title, item: `/blog/${post.slug}` },
                ]),
              ]),
            ),
          }}
        />
      </main>
      <PatreonCTA />
      <PublicFooter />
    </>
  );
}
