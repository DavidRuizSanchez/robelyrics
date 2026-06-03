"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

// Una pista de la cola. Los slugs son opcionales: permiten enlazar el título de
// "sonando ahora" a su página de canción. `seconds` arranca el vídeo en un
// punto concreto (lo usa YoutubeLink para reproducir un fragmento citado).
export type PlayerTrack = {
  videoId: string;
  title: string;
  artist?: string;
  artistSlug?: string;
  albumSlug?: string;
  songSlug?: string;
  seconds?: number | null;
};

type Ctx = {
  queue: PlayerTrack[];
  index: number; // -1 si no hay nada cargado
  current: PlayerTrack | null;
  isPlaying: boolean;
  // Reemplaza la cola entera y empieza a sonar desde startIndex.
  playQueue: (tracks: PlayerTrack[], startIndex?: number) => void;
  // Reproduce una sola pista ya (reemplaza la cola). Alias retrocompatible: open.
  playNow: (track: PlayerTrack) => void;
  open: (track: PlayerTrack) => void;
  // Añade al final de la cola sin interrumpir lo que suena.
  enqueue: (tracks: PlayerTrack | PlayerTrack[]) => void;
  next: () => void;
  prev: () => void;
  jumpTo: (i: number) => void;
  removeAt: (i: number) => void;
  close: () => void;
  setIsPlaying: (b: boolean) => void;
  hasNext: boolean;
  hasPrev: boolean;
};

const Context = createContext<Ctx | null>(null);

export function YoutubePlayerProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<PlayerTrack[]>([]);
  const [index, setIndex] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);

  const playQueue = useCallback((tracks: PlayerTrack[], startIndex = 0) => {
    const clean = tracks.filter((t) => t.videoId);
    if (clean.length === 0) return;
    setQueue(clean);
    setIndex(Math.min(Math.max(0, startIndex), clean.length - 1));
  }, []);

  const playNow = useCallback((track: PlayerTrack) => {
    if (!track.videoId) return;
    setQueue([track]);
    setIndex(0);
  }, []);

  const enqueue = useCallback((t: PlayerTrack | PlayerTrack[]) => {
    const items = (Array.isArray(t) ? t : [t]).filter((x) => x.videoId);
    if (items.length === 0) return;
    setQueue((q) => [...q, ...items]);
    // Si no había nada sonando, arranca por lo recién añadido.
    setIndex((i) => (i < 0 ? 0 : i));
  }, []);

  const next = useCallback(() => {
    setIndex((i) => (i < queue.length - 1 ? i + 1 : i));
  }, [queue.length]);

  const prev = useCallback(() => {
    setIndex((i) => (i > 0 ? i - 1 : i));
  }, []);

  const jumpTo = useCallback(
    (i: number) => {
      setIndex((cur) => (i >= 0 && i < queue.length ? i : cur));
    },
    [queue.length],
  );

  const removeAt = useCallback(
    (i: number) => {
      setQueue((q) => q.filter((_, idx) => idx !== i));
      setIndex((cur) => {
        if (i < cur) return cur - 1;
        if (i === cur) return Math.min(cur, queue.length - 2);
        return cur;
      });
    },
    [queue.length],
  );

  const close = useCallback(() => {
    setQueue([]);
    setIndex(-1);
    setIsPlaying(false);
  }, []);

  const value = useMemo<Ctx>(
    () => ({
      queue,
      index,
      current: index >= 0 && index < queue.length ? queue[index] : null,
      isPlaying,
      playQueue,
      playNow,
      open: playNow,
      enqueue,
      next,
      prev,
      jumpTo,
      removeAt,
      close,
      setIsPlaying,
      hasNext: index >= 0 && index < queue.length - 1,
      hasPrev: index > 0,
    }),
    [
      queue,
      index,
      isPlaying,
      playQueue,
      playNow,
      enqueue,
      next,
      prev,
      jumpTo,
      removeAt,
      close,
    ],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useYoutubePlayer(): Ctx {
  const c = useContext(Context);
  if (!c) {
    throw new Error("useYoutubePlayer must be inside YoutubePlayerProvider");
  }
  return c;
}
