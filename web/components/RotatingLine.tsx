"use client";

import { useEffect, useState } from "react";
import { ROTATING_LINES } from "@/lib/discography-display";

/**
 * Frase rotativa con fade-out 400ms. Para el Hero.
 */
export default function RotatingLine({
  intervalMs = 5500,
}: {
  intervalMs?: number;
}) {
  const [idx, setIdx] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const t = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIdx((i) => (i + 1) % ROTATING_LINES.length);
        setVisible(true);
      }, 400);
    }, intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);

  const line = ROTATING_LINES[idx];

  return (
    <div
      style={{ opacity: visible ? 1 : 0, transition: "opacity 400ms ease" }}
    >
      <p className="font-serif italic text-2xl md:text-3xl text-ink m-0 leading-snug">
        «{line.text}»
      </p>
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-2.5">
        · {line.song} · {line.album} · {line.year}
      </p>
    </div>
  );
}
