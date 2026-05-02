"use client";

import { useEffect, useState } from "react";
import { T } from "@/lib/theme";

/**
 * Cursor granate personalizado. Solo en `pointer: fine` (desktop con ratón).
 * Se agranda al pasar sobre links/buttons o elementos con [data-cursor=hover].
 */
export default function InkCursor() {
  const [pos, setPos] = useState({ x: -100, y: -100 });
  const [hovering, setHovering] = useState(false);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia("(pointer: coarse)").matches) return;
    setEnabled(true);

    const move = (e: MouseEvent) => {
      setPos({ x: e.clientX, y: e.clientY });
      const t = e.target as HTMLElement | null;
      const interactive = !!t?.closest?.(
        "button, a, [role=button], input, textarea, [data-cursor=hover]"
      );
      setHovering(interactive);
    };
    window.addEventListener("mousemove", move);
    return () => window.removeEventListener("mousemove", move);
  }, []);

  if (!enabled) return null;

  const size = hovering ? 36 : 10;
  return (
    <div
      aria-hidden
      style={{
        position: "fixed",
        pointerEvents: "none",
        left: pos.x - size / 2,
        top: pos.y - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        background: hovering ? "transparent" : T.accent,
        border: hovering ? `1.5px solid ${T.accent}` : "none",
        boxShadow: `0 0 14px ${T.accent}66`,
        transition:
          "width 220ms cubic-bezier(.2,.8,.2,1), height 220ms cubic-bezier(.2,.8,.2,1)",
        zIndex: 99999,
      }}
    />
  );
}
