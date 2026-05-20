import type { Metadata } from "next";
import TaxonomyListLayout from "@/components/TaxonomyListLayout";
import { apiFetch } from "@/lib/api";
import type { PublicTaxonomyListItem } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Geografía · Lugares reales en las canciones de Extremoduro y Robe · Entre Interiores",
  description:
    "Cáceres, Extremadura, Plasencia: los lugares reales que aparecen nombrados en las canciones de Extremoduro y Robe.",
  alternates: { canonical: `${SITE_URL}/lugares` },
};

export default async function LugaresPage() {
  let items: PublicTaxonomyListItem[] = [];
  try {
    items = await apiFetch<PublicTaxonomyListItem[]>("/public/places", {
      authenticated: false,
    });
  } catch {
    items = [];
  }

  return (
    <TaxonomyListLayout
      hubSlug="lugares"
      hubLabel="Geografía"
      hubTitle="Geografía"
      hubLead="Los lugares reales que aparecen · nombrados con su nombre · en las canciones de Extremoduro y Robe. Ciudades, regiones, sitios físicos del mapa. Cuando una letra menciona un lugar concreto, está aquí. Los símbolos y figuras del cancionero viven en el bestiario."
      items={items}
    />
  );
}
