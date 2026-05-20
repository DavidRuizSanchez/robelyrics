// Constructor de JSON-LD con @graph interconectado entre páginas.
//
// Idea: cada entidad (Artist, Album, Song, Person) tiene un `@id` canónico
// derivado de su URL pública. En cualquier página, los nodos relacionados
// se incluyen mínimamente y referencian otros nodos por @id. Así Google
// puede unificar la entidad cross-page como una sola del knowledge graph.
//
// URI canónica por tipo:
//   MusicGroup:        {SITE_URL}/{artist-slug}#musicgroup
//   MusicAlbum:        {SITE_URL}/{artist-slug}/{album-slug}#musicalbum
//   MusicComposition:  {SITE_URL}/{artist-slug}/{album-slug}/{song-slug}#musiccomposition
//   Person:            {SITE_URL}/personas/{person-slug}#person

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const canonical = {
  musicGroup: (artistSlug: string) =>
    `${SITE_URL}/${artistSlug}#musicgroup`,
  musicAlbum: (artistSlug: string, albumSlug: string) =>
    `${SITE_URL}/${artistSlug}/${albumSlug}#musicalbum`,
  musicComposition: (
    artistSlug: string,
    albumSlug: string,
    songSlug: string,
  ) => `${SITE_URL}/${artistSlug}/${albumSlug}/${songSlug}#musiccomposition`,
  person: (personSlug: string) =>
    `${SITE_URL}/personas/${personSlug}#person`,
};

export const urls = {
  artist: (artistSlug: string) => `${SITE_URL}/${artistSlug}`,
  album: (artistSlug: string, albumSlug: string) =>
    `${SITE_URL}/${artistSlug}/${albumSlug}`,
  song: (artistSlug: string, albumSlug: string, songSlug: string) =>
    `${SITE_URL}/${artistSlug}/${albumSlug}/${songSlug}`,
  person: (personSlug: string) => `${SITE_URL}/personas/${personSlug}`,
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
    inAlbum: { "@id": canonical.musicAlbum(song.artistSlug, song.albumSlug) },
  };
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
    "@graph": nodes,
  };
}
