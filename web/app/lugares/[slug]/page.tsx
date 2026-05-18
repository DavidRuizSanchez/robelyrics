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
    const d = await apiFetch<PublicTaxonomyDetail>(`/public/places/${slug}`, {
      authenticated: false,
    });
    return {
      title: `${d.name} · Canciones de Extremoduro y Robe · Entre Interiores`,
      description:
        d.description ||
        `Canciones de Extremoduro y Robe que mencionan o sitúan su escena en ${d.name}.`,
      alternates: { canonical: `${SITE_URL}/lugares/${d.slug}` },
    };
  } catch {
    return {};
  }
}

export default async function PlaceDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let detail: PublicTaxonomyDetail;
  try {
    detail = await apiFetch<PublicTaxonomyDetail>(`/public/places/${slug}`, {
      authenticated: false,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return <TaxonomyDetailLayout hubSlug="lugares" hubLabel="Geografía" detail={detail} />;
}
