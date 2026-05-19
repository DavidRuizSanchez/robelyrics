// Tipos de respuesta del API. Reflejan los schemas Pydantic en api/app/routers/.

export type Artist = {
  slug: string;
  name: string;
  active_years: string | null;
};

export type Album = {
  slug: string;
  title: string;
  year: number;
  kind: string;
  cover_url?: string | null;
};

export type Track = {
  slug: string;
  title: string;
  track_number: number | null;
  has_interpretation: boolean;
  youtube_id?: string | null;
};

export type AlbumDetail = Album & {
  artist: Artist;
  tracks: Track[];
};

export type LyricLine = {
  line_index: number;
  stanza_index: number;
  text: string;
  start_seconds: number | null;
};

export type KeyMetaphor = {
  phrase: string;
  meaning: string;
  source_ids: number[];
};

export type Theme = {
  theme: string;
  source_ids: number[];
};

export type Reference = {
  type: "biographical" | "intertextual" | "cultural";
  description: string;
  source_ids: number[];
};

export type Interpretation = {
  themes: Theme[];
  key_metaphors: KeyMetaphor[];
  references: Reference[];
  fan_consensus: string;
  fan_consensus_citations: number[];
};

export type SongDetail = {
  slug: string;
  title: string;
  track_number: number | null;
  artist: Artist;
  album: Album;
  lines: LyricLine[];
  interpretation: Interpretation | null;
  interpretation_confidence: "high" | "medium" | "low" | null;
  youtube_id: string | null;
};

// /search/semantic
export type SemanticHit = {
  line_text: string;
  song: { id: number; title: string; slug: string; youtube_id?: string | null };
  album: { title: string; slug: string; year: number };
  artist: { slug: string; name: string };
  line_index: number | null;
  start_seconds: number | null;
  context_before: string[];
  context_after: string[];
  fan_context: string | null;
  fan_context_sources: { source_id: number }[];
  why: string;
};

export type SemanticOut = {
  query: string;
  results: SemanticHit[];
};

// /search/complete
export type CompleteHit = {
  matched_line: string;
  continuation_lines: string[];
  start_seconds: number | null;
  song: { id: number; title: string; slug: string; youtube_id?: string | null };
  album: { title: string; slug: string; year: number | null };
  artist: { slug: string; name: string };
};

export type CompleteOut = {
  query: string;
  results: CompleteHit[];
};

// /public/search — buscador público sin auth (títulos + letras)
export type PublicSearchHit = {
  kind: "artist" | "album" | "song";
  slug: string;
  title: string;
  subtitle: string | null;
  url_path: string;
  lyric_match?: string | null;
};

export type PublicSearchOut = {
  query: string;
  results: PublicSearchHit[];
};

export type AuthMe = {
  id: number;
  email: string;
  is_active: boolean;
  is_admin: boolean;
};

// ----- Pública (capa SEO sin auth) ----- //

export type PublicArtistOut = {
  slug: string;
  name: string;
  active_years: string | null;
};

export type PublicAlbumOut = {
  slug: string;
  title: string;
  year: number;
  kind: string;
  cover_url: string | null;
};

export type PublicTrackOut = {
  slug: string;
  title: string;
  track_number: number | null;
  youtube_id: string | null;
};

export type PublicArtistMember = {
  slug: string;
  full_name: string;
  stage_name: string | null;
  role: string;
  era: string | null;
  is_founder: boolean;
  image_url: string | null;
};

export type PublicArtistDetail = PublicArtistOut & {
  albums: PublicAlbumOut[];
  members: PublicArtistMember[];
  seo_body: string | null;
  seo_meta_title: string | null;
  seo_meta_description: string | null;
  seo_h1: string | null;
};

export type PublicAlbumDetail = PublicAlbumOut & {
  artist: PublicArtistOut;
  tracks: PublicTrackOut[];
  seo_body: string | null;
  seo_meta_title: string | null;
  seo_meta_description: string | null;
  seo_h1: string | null;
};

export type PublicTaxonomyPill = {
  kind: "theme" | "place" | "concept";
  slug: string;
  name: string;
};

export type PublicSongDetail = {
  slug: string;
  title: string;
  track_number: number | null;
  artist: PublicArtistOut;
  album: PublicAlbumOut;
  /** Cover propia de la canción si tiene single/clip con artwork distinto. */
  cover_url: string | null;
  snippet: string[];
  snippet_attribution: string;
  genius_url: string | null;
  youtube_id: string | null;
  seo_body: string | null;
  seo_meta_title: string | null;
  seo_meta_description: string | null;
  seo_h1: string | null;
  themes: PublicTaxonomyPill[];
  places: PublicTaxonomyPill[];
  concepts: PublicTaxonomyPill[];
};

// /public/themes, /public/places, /public/concepts
export type PublicTaxonomyListItem = {
  slug: string;
  name: string;
  description: string | null;
  song_count: number;
};

export type PublicTaxonomySongRef = {
  title: string;
  url_path: string;
  artist_name: string;
  album_title: string;
  year: number | null;
};

export type PublicTaxonomyDetail = {
  slug: string;
  name: string;
  description: string | null;
  kind: "theme" | "place" | "concept";
  extra: { geo_lat?: number | null; geo_lng?: number | null; kind?: string | null } | null;
  songs: PublicTaxonomySongRef[];
};

// /public/posts — blog público
export type PublicPostListItem = {
  slug: string;
  kind: "editorial" | "news" | "anniversary";
  title: string;
  excerpt: string | null;
  hero_image_url: string | null;
  published_at: string;
};

export type PublicPostDetail = PublicPostListItem & {
  body_md: string;
  meta_title: string | null;
  meta_description: string | null;
  source_url: string | null;
  source_name: string | null;
  anniversary_year: number | null;
};
