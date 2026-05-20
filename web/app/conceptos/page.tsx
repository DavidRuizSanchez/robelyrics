import type { Metadata } from "next";
import TaxonomyListLayout from "@/components/TaxonomyListLayout";
import { apiFetch } from "@/lib/api";
import type { PublicTaxonomyListItem } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Símbolos y figuras recurrentes · Extremoduro y Robe · Entre Interiores",
  description:
    "El águila, las flores amarillas, el delfín, la hoguera, los animales: los símbolos que se repiten en el cancionero de Extremoduro y Robe.",
  alternates: { canonical: `${SITE_URL}/conceptos` },
};

export default async function ConceptosPage() {
  let items: PublicTaxonomyListItem[] = [];
  try {
    items = await apiFetch<PublicTaxonomyListItem[]>("/public/concepts", {
      authenticated: false,
    });
  } catch {
    items = [];
  }

  return (
    <TaxonomyListLayout
      hubSlug="conceptos"
      hubLabel="Bestiario"
      hubTitle="Bestiario"
      hubLead="Las imágenes que reaparecen disco tras disco: el águila, el sol y la nube, las flores amarillas, los animales del cancionero, las ballenas. Pequeño bestiario simbólico de Extremoduro y Robe."
      items={items}
    />
  );
}
