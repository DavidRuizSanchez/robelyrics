import { safeJsonLd } from "@/lib/safe-json-ld";
import { breadcrumbListNode, buildGraph, webPageNode } from "@/lib/schema-graph";

// Schema mínimo para las páginas legales (comparten layout sin Breadcrumbs):
// un WebPage por ruta + su BreadcrumbList, todo dentro de un @graph que
// referencia el WebSite/Organization globales por @id.
export default function LegalSchema({
  path,
  name,
}: {
  path: string;
  name: string;
}) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: safeJsonLd(
          buildGraph([
            webPageNode({ path, name, type: "WebPage" }),
            breadcrumbListNode(path, [
              { name: "Entre Interiores", item: "/" },
              { name, item: path },
            ]),
          ]),
        ),
      }}
    />
  );
}
