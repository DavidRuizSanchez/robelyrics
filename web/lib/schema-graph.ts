// Constructor de JSON-LD con @graph interconectado entre páginas.
//
// Idea: cada entidad tiene un `@id` canónico derivado de su URL pública. En
// cualquier página, los nodos relacionados se incluyen mínimamente y
// referencian otros nodos por @id. Así Google unifica la entidad cross-page
// como una sola del knowledge graph. TODA página pública emite UN `@graph`
// (buildGraph) con su WebPage + BreadcrumbList + entidad(es) + refs.
//
// URI canónica por tipo:
//   WebSite:           {SITE}/#website          (layout)
//   Organization:      {SITE}/#organization     (layout, publisher)
//   Person (autor):    https://davidruizsanchez.es/#person  (externo)
//   MusicGroup:        {SITE}/{artist}#musicgroup
//   MusicAlbum:        {SITE}/{artist}/{album}#musicalbum
//   MusicComposition:  {SITE}/{artist}/{album}/{song}#musiccomposition
//   MusicRecording:    {SITE}/{artist}/{album}/{song}#musicrecording
//   Person (corpus):   {SITE}/personas/{slug}#person
//   Band/sello:        {SITE}/grupos/{slug}#musicgroup | #organization
//   Article:           {SITE}/blog/{slug}#article
//   Blog:              {SITE}/blog#blog
//   Taxonomy:          {SITE}/{temas|lugares|conceptos}/{slug}#definedterm | #place
//   WebPage:           {SITE}{path}#webpage
//   BreadcrumbList:    {SITE}{path}#breadcrumb
//   ItemList:          {SITE}{path}#itemlist
//   ImageObject:       {SITE}{path}#primaryimage

import {
  AUTHOR_ID,
  ORGANIZATION_ID,
  SITE_ALT_NAME,
  SITE_DESCRIPTION,
  SITE_INSTAGRAM,
  SITE_LANG,
  SITE_LOGO_URL,
  SITE_NAME,
  SITE_URL,
  WEBSITE_ID,
} from "@/lib/site";

export type TaxonomyKind = "theme" | "place" | "concept";
const TAX_PATH: Record<TaxonomyKind, string> = {
  theme: "temas",
  place: "lugares",
  concept: "conceptos",
};
const TAX_FRAG: Record<TaxonomyKind, string> = {
  theme: "definedterm",
  place: "place",
  concept: "definedterm",
};

export const canonical = {
  website: WEBSITE_ID,
  organization: ORGANIZATION_ID,
  musicGroup: (artistSlug: string) => `${SITE_URL}/${artistSlug}#musicgroup`,
  musicAlbum: (artistSlug: string, albumSlug: string) =>
    `${SITE_URL}/${artistSlug}/${albumSlug}#musicalbum`,
  musicComposition: (artistSlug: string, albumSlug: string, songSlug: string) =>
    `${SITE_URL}/${artistSlug}/${albumSlug}/${songSlug}#musiccomposition`,
  musicRecording: (artistSlug: string, albumSlug: string, songSlug: string) =>
    `${SITE_URL}/${artistSlug}/${albumSlug}/${songSlug}#musicrecording`,
  person: (personSlug: string) => `${SITE_URL}/personas/${personSlug}#person`,
  band: (slug: string, isLabel = false) =>
    `${SITE_URL}/grupos/${slug}#${isLabel ? "organization" : "musicgroup"}`,
  article: (slug: string) => `${SITE_URL}/blog/${slug}#article`,
  blog: `${SITE_URL}/blog#blog`,
  taxonomy: (kind: TaxonomyKind, slug: string) =>
    `${SITE_URL}/${TAX_PATH[kind]}/${slug}#${TAX_FRAG[kind]}`,
  webPage: (path: string) => `${SITE_URL}${path}#webpage`,
  breadcrumb: (path: string) => `${SITE_URL}${path}#breadcrumb`,
  itemList: (path: string) => `${SITE_URL}${path}#itemlist`,
  primaryImage: (path: string) => `${SITE_URL}${path}#primaryimage`,
};

export const urls = {
  artist: (artistSlug: string) => `${SITE_URL}/${artistSlug}`,
  album: (artistSlug: string, albumSlug: string) =>
    `${SITE_URL}/${artistSlug}/${albumSlug}`,
  song: (artistSlug: string, albumSlug: string, songSlug: string) =>
    `${SITE_URL}/${artistSlug}/${albumSlug}/${songSlug}`,
  person: (personSlug: string) => `${SITE_URL}/personas/${personSlug}`,
  band: (slug: string) => `${SITE_URL}/grupos/${slug}`,
  taxonomy: (kind: TaxonomyKind, slug: string) =>
    `${SITE_URL}/${TAX_PATH[kind]}/${slug}`,
  blogPost: (slug: string) => `${SITE_URL}/blog/${slug}`,
  page: (path: string) => `${SITE_URL}${path}`,
};

// --------------------------------------------------------------------------- //
// Tipos de entrada
// --------------------------------------------------------------------------- //
export type AlbumInput = {
  slug: string;
  artistSlug: string;
  title: string;
  year: number;
  coverUrl?: string | null;
  tracks?: { slug: string; title: string }[];
};

export type ArtistInput = {
  slug: string;
  name: string;
  activeYears?: string | null;
  albums?: AlbumInput[];
  members?: PersonInput[];
};

export type SongInput = {
  slug: string;
  artistSlug: string;
  albumSlug: string;
  albumTitle: string;
  albumYear: number;
  artistName: string;
  title: string;
};

export type PersonInput = {
  slug: string;
  fullName: string;
  stageName?: string | null;
  birthDate?: string | null;
  deathDate?: string | null;
  birthPlace?: string | null;
  imageUrl?: string | null;
  wikipediaUrl?: string | null;
  wikidataId?: string | null;
  memberOf?: { artistSlug: string; artistName: string }[];
};

// --------------------------------------------------------------------------- //
// Constructores de nodos
// --------------------------------------------------------------------------- //
export function musicGroupNode(artist: ArtistInput): Record<string, unknown> {
  const node: Record<string, unknown> = {
    "@type": "MusicGroup",
    "@id": canonical.musicGroup(artist.slug),
    name: artist.name,
    url: urls.artist(artist.slug),
  };
  if (artist.activeYears) node.foundingDate = artist.activeYears.split("-")[0];
  if (artist.albums && artist.albums.length > 0) {
    node.album = artist.albums.map((a) => ({
      "@id": canonical.musicAlbum(a.artistSlug, a.slug),
    }));
  }
  if (artist.members && artist.members.length > 0) {
    node.member = artist.members.map((m) => ({
      "@id": canonical.person(m.slug),
    }));
  }
  return node;
}

export function musicAlbumNode(album: AlbumInput): Record<string, unknown> {
  const node: Record<string, unknown> = {
    "@type": "MusicAlbum",
    "@id": canonical.musicAlbum(album.artistSlug, album.slug),
    name: album.title,
    datePublished: String(album.year),
    url: urls.album(album.artistSlug, album.slug),
    byArtist: { "@id": canonical.musicGroup(album.artistSlug) },
  };
  if (album.coverUrl) node.image = album.coverUrl;
  if (album.tracks && album.tracks.length > 0) {
    node.numTracks = album.tracks.length;
    node.track = album.tracks.map((t) => ({
      "@id": canonical.musicComposition(album.artistSlug, album.slug, t.slug),
    }));
  }
  return node;
}

export function musicCompositionNode(
  song: SongInput,
): Record<string, unknown> {
  return {
    "@type": "MusicComposition",
    "@id": canonical.musicComposition(
      song.artistSlug,
      song.albumSlug,
      song.slug,
    ),
    name: song.title,
    url: urls.song(song.artistSlug, song.albumSlug, song.slug),
    composer: { "@id": canonical.musicGroup(song.artistSlug) },
    // isPartOf (de CreativeWork) en vez de inAlbum (que es de MusicRecording,
    // no de MusicComposition, y daba warning de validación).
    isPartOf: { "@id": canonical.musicAlbum(song.artistSlug, song.albumSlug) },
  };
}

export type VideoInput = {
  artistSlug: string;
  albumSlug: string;
  songSlug: string;
  songTitle: string;
  artistName: string;
  youtubeId: string;
  videoTitle?: string | null;
  uploadDate?: string | null; // ISO-8601
  durationSec?: number | null;
};

// VideoObject para la página de canción cuando hay vídeo de YouTube embebido.
// Enlaza con la MusicComposition por @id (knowledge graph unificado).
export function videoObjectNode(v: VideoInput): Record<string, unknown> {
  const node: Record<string, unknown> = {
    "@type": "VideoObject",
    name: v.videoTitle || `${v.songTitle} · ${v.artistName}`,
    description: `Vídeo de «${v.songTitle}» de ${v.artistName} en Entre Interiores.`,
    thumbnailUrl: [
      `https://i.ytimg.com/vi/${v.youtubeId}/maxresdefault.jpg`,
      `https://i.ytimg.com/vi/${v.youtubeId}/hqdefault.jpg`,
    ],
    contentUrl: `https://www.youtube.com/watch?v=${v.youtubeId}`,
    embedUrl: `https://www.youtube.com/embed/${v.youtubeId}`,
    // El vídeo trata sobre la composición (about acepta Thing; associatedMedia
    // exigía un MediaObject y daba error de validación).
    about: {
      "@id": canonical.musicComposition(v.artistSlug, v.albumSlug, v.songSlug),
    },
  };
  if (v.uploadDate) node.uploadDate = v.uploadDate;
  if (v.durationSec) node.duration = `PT${v.durationSec}S`;
  return node;
}

export function personNode(person: PersonInput): Record<string, unknown> {
  const node: Record<string, unknown> = {
    "@type": "Person",
    "@id": canonical.person(person.slug),
    name: person.fullName,
    url: urls.person(person.slug),
  };
  if (person.stageName && person.stageName !== person.fullName) {
    node.alternateName = person.stageName;
  }
  if (person.birthDate) node.birthDate = person.birthDate;
  if (person.deathDate) node.deathDate = person.deathDate;
  if (person.birthPlace) {
    node.birthPlace = { "@type": "Place", name: person.birthPlace };
  }
  if (person.imageUrl) node.image = person.imageUrl;
  const sameAs: string[] = [];
  if (person.wikipediaUrl) sameAs.push(person.wikipediaUrl);
  if (person.wikidataId) {
    sameAs.push(`https://www.wikidata.org/wiki/${person.wikidataId}`);
  }
  if (sameAs.length > 0) node.sameAs = sameAs;
  if (person.memberOf && person.memberOf.length > 0) {
    node.memberOf = person.memberOf.map((m) => ({
      "@id": canonical.musicGroup(m.artistSlug),
    }));
  }
  return node;
}

// --------------------------------------------------------------------------- //
// Mentions: convierte el array de `entities` del backend en nodos schema.org
// --------------------------------------------------------------------------- //
export type ResolvedEntity = {
  type: string;
  name: string;
  canonical_id: string | null;
  url: string | null;
  same_as: string[];
  from_corpus: boolean;
};

export function mentionNode(e: ResolvedEntity): Record<string, unknown> {
  const node: Record<string, unknown> = {
    "@type": e.type || "Thing",
    name: e.name,
  };
  if (e.canonical_id) node["@id"] = e.canonical_id;
  if (e.url) node.url = e.url;
  if (e.same_as && e.same_as.length > 0) node.sameAs = e.same_as;
  return node;
}

export function mentionsArray(
  entities: ResolvedEntity[] | undefined | null,
): Record<string, unknown>[] {
  if (!entities || entities.length === 0) return [];
  return entities.map(mentionNode);
}

// --------------------------------------------------------------------------- //
// Graph builder
// --------------------------------------------------------------------------- //
export function buildGraph(
  nodes: Record<string, unknown>[],
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@graph": nodes.filter(Boolean),
  };
}

// --------------------------------------------------------------------------- //
// Nodos GLOBALES (los emite el layout una vez; las páginas los referencian)
// --------------------------------------------------------------------------- //
export function webSiteNode(): Record<string, unknown> {
  return {
    "@type": "WebSite",
    "@id": WEBSITE_ID,
    url: SITE_URL,
    name: SITE_NAME,
    alternateName: SITE_ALT_NAME,
    description: SITE_DESCRIPTION,
    inLanguage: SITE_LANG,
    publisher: { "@id": ORGANIZATION_ID },
    creator: { "@id": AUTHOR_ID },
    sameAs: [SITE_INSTAGRAM],
    potentialAction: {
      "@type": "SearchAction",
      target: {
        "@type": "EntryPoint",
        urlTemplate: `${SITE_URL}/buscar?q={search_term_string}`,
      },
      "query-input": "required name=search_term_string",
    },
  };
}

export function organizationNode(): Record<string, unknown> {
  return {
    "@type": "Organization",
    "@id": ORGANIZATION_ID,
    name: SITE_NAME,
    alternateName: SITE_ALT_NAME,
    url: SITE_URL,
    logo: { "@type": "ImageObject", url: SITE_LOGO_URL },
    sameAs: [SITE_INSTAGRAM],
  };
}

export function authorPersonNode(): Record<string, unknown> {
  return {
    "@type": "Person",
    "@id": AUTHOR_ID,
    name: "David Ruiz Sánchez",
    givenName: "David",
    familyName: "Ruiz Sánchez",
    url: "https://davidruizsanchez.es",
    jobTitle: "Partner & Head of SEO",
    worksFor: { "@type": "Organization", name: "Convertix", url: "https://convertix.net" },
    sameAs: [
      "https://www.linkedin.com/in/davidruizsanchez/",
      "https://github.com/DavidRuizSanchez",
      "https://x.com/davidruiz_s",
    ],
  };
}

export function siteGraphNodes(): Record<string, unknown>[] {
  return [webSiteNode(), organizationNode(), authorPersonNode()];
}

// --------------------------------------------------------------------------- //
// Nodos de PÁGINA (van en el @graph de cada página)
// --------------------------------------------------------------------------- //
export type WebPageInput = {
  path: string;
  name: string;
  type?: string; // WebPage | CollectionPage | ProfilePage | AboutPage | SearchResultsPage | ItemPage
  description?: string | null;
  mainEntityId?: string | null;
  primaryImageId?: string | null;
  breadcrumb?: boolean; // por defecto true
  datePublished?: string | null;
  dateModified?: string | null;
};

export function webPageNode(input: WebPageInput): Record<string, unknown> {
  const node: Record<string, unknown> = {
    "@type": input.type || "WebPage",
    "@id": canonical.webPage(input.path),
    url: urls.page(input.path),
    name: input.name,
    isPartOf: { "@id": WEBSITE_ID },
    inLanguage: SITE_LANG,
  };
  if (input.description) node.description = input.description;
  if (input.mainEntityId) node.mainEntity = { "@id": input.mainEntityId };
  if (input.primaryImageId) {
    node.primaryImageOfPage = { "@id": input.primaryImageId };
  }
  if (input.breadcrumb !== false) {
    node.breadcrumb = { "@id": canonical.breadcrumb(input.path) };
  }
  if (input.datePublished) node.datePublished = input.datePublished;
  if (input.dateModified) node.dateModified = input.dateModified;
  return node;
}

export type Crumb = { name: string; item: string }; // item: ruta relativa o URL absoluta

export function breadcrumbListNode(
  path: string,
  items: Crumb[],
): Record<string, unknown> {
  return {
    "@type": "BreadcrumbList",
    "@id": canonical.breadcrumb(path),
    itemListElement: items.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.name,
      item: c.item.startsWith("http") ? c.item : `${SITE_URL}${c.item}`,
    })),
  };
}

export type ListEntry = { name: string; url: string; id?: string | null };

export function itemListNode(
  path: string,
  items: ListEntry[],
): Record<string, unknown> {
  return {
    "@type": "ItemList",
    "@id": canonical.itemList(path),
    numberOfItems: items.length,
    itemListElement: items.map((it, i) => {
      const li: Record<string, unknown> = {
        "@type": "ListItem",
        position: i + 1,
        url: it.url.startsWith("http") ? it.url : `${SITE_URL}${it.url}`,
        name: it.name,
      };
      if (it.id) li.item = { "@id": it.id };
      return li;
    }),
  };
}

export type ImageInput = {
  url: string;
  path?: string; // si se da, asigna @id {SITE}{path}#primaryimage
  attribution?: string | null;
  license?: string | null;
  sourceUrl?: string | null;
};

// Imagen como ImageObject con atribución/licencia (contenido CC que conviene
// acreditar). Devuelve null si no hay url.
export function imageObjectNode(input: ImageInput): Record<string, unknown> | null {
  if (!input.url) return null;
  const node: Record<string, unknown> = {
    "@type": "ImageObject",
    url: input.url,
    contentUrl: input.url,
  };
  if (input.path) node["@id"] = canonical.primaryImage(input.path);
  if (input.attribution) {
    node.creditText = input.attribution
      .replace(/^\*|\*$/g, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .trim();
  }
  if (input.license) node.license = input.license;
  if (input.sourceUrl) node.isBasedOnUrl = input.sourceUrl;
  return node;
}

// DORMIDO: builder listo para el futuro podcast (sin datos aún). No se usa.
export type PodcastEpisodeInput = {
  slug: string;
  title: string;
  audioUrl: string;
  description?: string | null;
  datePublished?: string | null;
  durationSec?: number | null;
};
export function podcastEpisodeNode(
  ep: PodcastEpisodeInput,
): Record<string, unknown> {
  const node: Record<string, unknown> = {
    "@type": "PodcastEpisode",
    "@id": `${SITE_URL}/podcast/${ep.slug}#episode`,
    name: ep.title,
    url: `${SITE_URL}/podcast/${ep.slug}`,
    associatedMedia: { "@type": "AudioObject", contentUrl: ep.audioUrl },
    partOfSeries: {
      "@type": "PodcastSeries",
      name: SITE_NAME,
      url: `${SITE_URL}/podcast`,
    },
  };
  if (ep.description) node.description = ep.description;
  if (ep.datePublished) node.datePublished = ep.datePublished;
  if (ep.durationSec) node.timeRequired = `PT${ep.durationSec}S`;
  return node;
}

// Quita @context de un objeto que ya lo traía, para meterlo como nodo de un
// @graph (las páginas que ya construían su objeto suelto lo reutilizan así).
export function asNode(
  obj: Record<string, unknown>,
): Record<string, unknown> {
  const copy = { ...obj };
  delete copy["@context"];
  return copy;
}
