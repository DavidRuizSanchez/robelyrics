import type { Metadata } from "next";
import { notFound } from "next/navigation";
import TaxonomyDetailLayout from "@/components/TaxonomyDetailLayout";
import { apiFetch, ApiError } from "@/lib/api";
import type { PublicTaxonomyDetail } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const d = await apiFetch<PublicTaxonomyDetail>(`/public/themes/${slug}`, {
      authenticated: false,
    });
    return {
      title:
        d.seo_meta_title ||
        `${d.name} · Canciones de Extremoduro y Robe · Entre Interiores`,
      description:
        d.seo_meta_description ||
        d.description ||
        `Canciones de Extremoduro y Robe sobre ${d.name.toLowerCase()}.`,
      alternates: { canonical: `${SITE_URL}/temas/${d.slug}` },
    };
  } catch {
    return {};
  }
}

export default async function ThemeDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let detail: PublicTaxonomyDetail;
  try {
    detail = await apiFetch<PublicTaxonomyDetail>(`/public/themes/${slug}`, {
      authenticated: false,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return <TaxonomyDetailLayout hubSlug="temas" hubLabel="Lo que aletea" detail={detail} />;
}
