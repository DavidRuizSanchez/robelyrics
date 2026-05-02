"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

/**
 * Context para sincronizar el reproductor karaoke con la lista de líneas.
 * El KaraokePlayer hace polling de YT.Player.getCurrentTime() y actualiza
 * `currentSeconds`. Cada <LyricLine> consume el contexto y decide su estilo
 * (activa, ya pasada, por venir).
 */

type Ctx = {
  currentSeconds: number | null;
  isPlaying: boolean;
  setCurrentSeconds: (s: number | null) => void;
  setIsPlaying: (p: boolean) => void;
};

const Context = createContext<Ctx | null>(null);

export function KaraokeProvider({ children }: { children: ReactNode }) {
  const [currentSeconds, setCurrentSeconds] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  return (
    <Context.Provider
      value={{ currentSeconds, isPlaying, setCurrentSeconds, setIsPlaying }}
    >
      {children}
    </Context.Provider>
  );
}

export function useKaraoke(): Ctx {
  const c = useContext(Context);
  if (!c) {
    throw new Error("useKaraoke must be inside KaraokeProvider");
  }
  return c;
}
