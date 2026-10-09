import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import RepertorioEnDirecto from "@/components/estudio/RepertorioEnDirecto";
import { ESTUDIOS, LICENCIA_CC_BY, estudioPorSlug } from "@/lib/estudios";
import { AUTHOR_ID } from "@/lib/site";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  breadcrumbListNode,
  buildGraph,
  canonical,
  urls,
  webPageNode,
} from "@/lib/schema-graph";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

// El registro vive en código, así que las rutas se conocen en build. Se
// enumeran (y no `[]` como en las plantillas que leen de la BD) porque son dos
// o tres y así se sirven estáticas desde el primer despliegue.
export function generateStaticParams() {
  return ESTUDIOS.map((e) => ({ slug: e.slug }));
}

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const estudio = estudioPorSlug(slug);
  if (!estudio) return {};
  return {
    title: `${estudio.metaTitle} · Entre Interiores`,
    description: estudio.metaDescription,
    alternates: { canonical: `${SITE_URL}/estudios/${estudio.slug}` },
    openGraph: {
      type: "article",
      title: estudio.metaTitle,
      description: estudio.metaDescription,
      url: `${SITE_URL}/estudios/${estudio.slug}`,
      publishedTime: estudio.datePublished,
    },
  };
}

export default async function EstudioPage({ params }: Props) {
  const { slug } = await params;
  const estudio = estudioPorSlug(slug);
  if (!estudio) notFound();

  const path = `/estudios/${estudio.slug}`;

  // Dataset además de Article: es lo que hace la pieza citable como fuente de
  // datos y no solo como artículo. `creator` apunta al nodo de autor del sitio.
  const datasetId = `${SITE_URL}${path}#dataset`;

  return (
    <>
      <PublicHeader />
      <main className="pt-6">
        <div className="px-5 md:px-14 max-w-[1040px] mx-auto">
          <Breadcrumbs
            items={[
              { label: "Entre Interiores", href: "/" },
              { label: "Estudios", href: "/estudios" },
              { label: estudio.titulo, href: path },
            ]}
          />
        </div>

        {estudio.slug === "repertorio-en-directo-extremoduro-robe" ? (
          <RepertorioEnDirecto />
        ) : null}

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                webPageNode({
                  path,
                  name: estudio.titulo,
                  description: estudio.metaDescription,
                  mainEntityId: datasetId,
                  datePublished: estudio.datePublished,
                  dateModified: estudio.dateModified,
                }),
                {
                  "@type": "Dataset",
                  "@id": datasetId,
                  name: estudio.titulo,
                  description: estudio.resumen,
                  url: urls.page(path),
                  inLanguage: "es",
                  datePublished: estudio.datePublished,
                  dateModified: estudio.dateModified,
                  creator: { "@id": AUTHOR_ID },
                  variableMeasured: estudio.mide,
                  isAccessibleForFree: true,
                  about: [
                    { "@id": canonical.musicGroup("extremoduro") },
                    { "@id": canonical.musicGroup("robe") },
                  ],
                  ...(estudio.post
                    ? { subjectOf: { "@id": canonical.article(estudio.post) } }
                    : {}),
                  ...(estudio.cobertura ? { temporalCoverage: estudio.cobertura } : {}),
                  ...(estudio.basadoEn ? { isBasedOn: estudio.basadoEn } : {}),
                  // La licencia cubre lo que se DESCARGA, que es solo material
                  // propio: las cifras de setlist.fm no se redistribuyen.
                  ...(estudio.descargas?.length
                    ? {
                        license: LICENCIA_CC_BY,
                        creditText: "Entre Interiores (entreinteriores.com)",
                        distribution: estudio.descargas.map((d) => ({
                          "@type": "DataDownload",
                          name: d.nombre,
                          encodingFormat: d.formato,
                          contentUrl: urls.page(d.ruta),
                          license: LICENCIA_CC_BY,
                        })),
                      }
                    : {}),
                },
                breadcrumbListNode(path, [
                  { name: "Entre Interiores", item: "/" },
                  { name: "Estudios", item: "/estudios" },
                  { name: estudio.titulo, item: path },
                ]),
              ]),
            ),
          }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
