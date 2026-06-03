import type { PlayerTrack } from "@/lib/youtube-player-context";

// Forma de pista que devuelve el API (/playlists/*), en snake_case.
export type PlaylistTrackOut = {
  video_id: string;
  title: string;
  artist: string;
  artist_slug: string;
  album_slug: string;
  song_slug: string;
  song_id?: number | null;
};

export type PlaylistSummary = { id: number; name: string; track_count: number };
export type PlaylistDetail = { id: number; name: string; tracks: PlaylistTrackOut[] };

// Convierte la pista del API en la que entiende el reproductor flotante.
export function toPlayerTrack(t: PlaylistTrackOut): PlayerTrack {
  return {
    videoId: t.video_id,
    title: t.title,
    artist: t.artist,
    artistSlug: t.artist_slug,
    albumSlug: t.album_slug,
    songSlug: t.song_slug,
  };
}
