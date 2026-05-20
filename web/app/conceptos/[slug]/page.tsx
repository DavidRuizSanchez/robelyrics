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
    const d = await apiFetch<PublicTaxonomyDetail>(`/public/concepts/${slug}`, {
      authenticated: false,
    });
    return {
      title:
        d.seo_meta_title ||
        `${d.name} · Símbolos en el cancionero · Entre Interiores`,
      description:
        d.seo_meta_description ||
        d.description ||
        `Canciones de Extremoduro y Robe donde aparece el símbolo "${d.name}".`,
      alternates: { canonical: `${SITE_URL}/conceptos/${d.slug}` },
    };
  } catch {
    return {};
  }
}

export default async function ConceptDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let detail: PublicTaxonomyDetail;
  try {
    detail = await apiFetch<PublicTaxonomyDetail>(`/public/concepts/${slug}`, {
      authenticated: false,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return <TaxonomyDetailLayout hubSlug="conceptos" hubLabel="Bestiario" detail={detail} />;
}
