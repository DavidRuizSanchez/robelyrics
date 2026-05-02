"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

type Player = {
  videoId: string;
  seconds?: number | null;
  title?: string;
  artist?: string;
};

type Ctx = {
  player: Player | null;
  open: (p: Player) => void;
  close: () => void;
};

const Context = createContext<Ctx | null>(null);

export function YoutubePlayerProvider({ children }: { children: ReactNode }) {
  const [player, setPlayer] = useState<Player | null>(null);
  return (
    <Context.Provider
      value={{
        player,
        open: (p) => setPlayer(p),
        close: () => setPlayer(null),
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function useYoutubePlayer(): Ctx {
  const c = useContext(Context);
  if (!c) {
    throw new Error("useYoutubePlayer must be inside YoutubePlayerProvider");
  }
  return c;
}
