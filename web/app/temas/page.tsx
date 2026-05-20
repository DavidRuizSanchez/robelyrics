import type { Metadata } from "next";
import TaxonomyListLayout from "@/components/TaxonomyListLayout";
import { apiFetch } from "@/lib/api";
import type { PublicTaxonomyListItem } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Lo que aletea · Temas en las canciones de Extremoduro y Robe · Entre Interiores",
  description:
    "Lo que aletea en las cabezas del cancionero: amor, lucha, muerte, libertad. Las canciones de Extremoduro y Robe agrupadas por los temas que las atraviesan.",
  alternates: { canonical: `${SITE_URL}/temas` },
};

export default async function TemasPage() {
  let items: PublicTaxonomyListItem[] = [];
  try {
    items = await apiFetch<PublicTaxonomyListItem[]>("/public/themes", {
      authenticated: false,
    });
  } catch {
    items = [];
  }

  return (
    <TaxonomyListLayout
      hubSlug="temas"
      hubLabel="Lo que aletea"
      hubTitle="Lo que aletea"
      hubLead="Los motivos que recorren la obra de Extremoduro y Robe. Lo que aletea, disco a disco, en las cabezas de los protagonistas de las canciones. Entra en cualquier tema para ver las canciones donde aparece."
      items={items}
    />
  );
}
