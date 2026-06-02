# Checklist de publicación — toda página nueva de entreinteriores.com

Estándar OBLIGATORIO para cualquier página/contenido nuevo (grupos, personas,
lugares, conceptos, discos, posts del blog…). Nada se marca `published=true`
sin cumplirlo y sin revisión humana (regla "nunca inventar en web pública").

## 1. Keyword objetivo (intención de búsqueda)
- Cada página responde a **UNA keyword principal** relevante (con volumen/intención
  real), reflejada en H1, `meta_title`, `meta_description` y el primer párrafo.
- Keywords secundarias/long-tail naturales en H2 y cuerpo, sin forzar.
- Investigación de KW: `/keyword-volume` (DataForSEO) / Ahrefs para volumen e intención.

## 2. Anti-canibalización (CRÍTICO)
- Antes de publicar, comprobar que la KW objetivo **no colisiona** con una página
  ya existente:
  - Buscar la KW en los `seo_content` existentes (meta_title / h1 / body) del corpus.
  - Cruzar con **GSC** (`/gsc-keywords` detecta canibalización; `/gsc` URL Inspection)
    para ver si ya hay una URL posicionando esa KW.
- Si hay colisión: **diferenciar la intención** (otra KW/ángulo) o **consolidar**
  (no crear la página y reforzar la existente). Documentar la decisión.

## 3. SEO on-page (ya automatizado en los generadores)
- `meta_title` ≤60 (incluye la KW) · `meta_description` ≤160 · canonical · OG.
- Jerarquía de headings: H1 = título; cuerpo en H2/H3 contiguos
  (`text_sanitizer.normalize_headings`, cableado en los generadores).
- Sin marcas de IA (em-dash, frases meta…): `strip_ai_tells`.

## 4. Enlazado interno
- Autolinker de corpus: hasta 4 enlaces a entidades relevantes con boost a las
  páginas débiles (`entity_resolver.autolink_corpus`, cableado).
- Módulo "En el diario": hasta 3 posts del blog relevantes (`RelatedPosts`).
- La nueva entidad debe entrar en `build_corpus_index` para recibir enlaces.

## 5. Datos estructurados (JSON-LD) — estándar `@graph` AUTOMÁTICO
- **Toda página publicada emite UN solo `@graph` de página** (además del `@graph`
  global que el `layout` inyecta en todas: `WebSite` + `Organization` + `Person`
  autor). Esto es automático: cualquier post/disco/canción/entidad nueva hereda
  el formato sin tocar nada, porque las plantillas dinámicas (`[slug]`,
  `[artist]/[album]/[song]`, etc.) ya construyen su `@graph`.
- **Cómo se construye** (no reinventar): `buildGraph([...])` de
  `web/lib/schema-graph.ts` + `safeJsonLd`. Marca y URLs salen de `web/lib/site.ts`
  (no redefinir `SITE_URL` ni hardcodear nombres).
- **Composición mínima de cada `@graph` de página**: nodo(s) de la entidad +
  `webPageNode(...)` (subtipo correcto: `CollectionPage`/`ProfilePage`/`ItemPage`/
  `AboutPage`/`SearchResultsPage`/`WebPage`) + `breadcrumbListNode(...)`. Los nodos
  referenciados (WebSite, Organization, álbum, grupo, persona…) van **por `@id`
  mínimo**, nunca reincluidos con datos.
- **`@id` canónicos** vía el helper `canonical.*` (un `@id` por entidad, reutilizado
  en todo el sitio → un único knowledge graph interconectado).
- Tipos por página: `MusicGroup`/`Organization`, `Person`, `Place`+geo,
  `MusicAlbum` (con `track`/`numTracks`), `MusicComposition` (`isPartOf`, NO
  `inAlbum`), `VideoObject` (`about` → composición, NO `associatedMedia`),
  `BlogPosting`/`NewsArticle`, `DefinedTerm`, `ItemList`, `BreadcrumbList`,
  `ImageObject` con atribución.
- **Si la página usa `<Breadcrumbs>`** (que ya NO emite su propio script), hay que
  añadir `breadcrumbListNode(path, [...])` a su `@graph` o se pierde el breadcrumb.
- **Páginas legales**: usar el componente `LegalSchema` (WebPage + breadcrumb).
- Validar: 1 script de página + 1 global (nunca un 3º), `@id` cruzados resuelven,
  Rich Results Test + Schema Markup Validator tras desplegar.

## 6. Imágenes
- Imagen relevante al tema con `alt` descriptivo. Foto CC real (Wikidata P18 →
  Wikimedia) para entidades concretas; arte IA (estética del proyecto) para
  abstractas. Atribución (autor + licencia) si es CC.
- Servir desde Cloudinary (no hot-link a Wikimedia: evita 429).

## 7. Publicación
- `published=true` solo tras revisión humana del contenido y del cumplimiento
  de este checklist.
- Tras publicar: revalidate de Next + alta en sitemap + verificación en vivo.

---

### Flujo recomendado para una entidad nueva
1. Sembrar (YAML + seed_*) y enriquecer (Wikidata/Wikipedia).
2. **Definir KW objetivo + chequeo anti-canibalización** (pasos 1-2).
3. Generar `seo_content` (genera meta/H1/cuerpo con la KW en mente).
4. Conseguir imagen + alt (paso 6).
5. Revisión humana → `published=true`.
6. Recalcular `related_posts` y `link_stats` (o esperar al cron semanal).
