import { T } from "@/lib/theme";

/**
 * Texto opacado y rotado para servir de marca de agua decorativa.
 * Server component (no usa state).
 */
export default function Watermark({
  text,
  size = "55vw",
  rotate = -2,
  bottom = "-10%",
  right = "-10%",
  opacity = 0.025,
  fontFamily = "var(--font-serif)",
}: {
  text: string;
  size?: string;
  rotate?: number;
  bottom?: string;
  right?: string;
  opacity?: number;
  fontFamily?: string;
}) {
  return (
    <div
      aria-hidden
      style={{
        position: "absolute",
        bottom,
        right,
        fontFamily,
        fontSize: size,
        fontWeight: 500,
        fontStyle: "italic",
        color: T.ink,
        opacity,
        transform: `rotate(${rotate}deg)`,
        pointerEvents: "none",
        userSelect: "none",
        lineHeight: 0.85,
        whiteSpace: "nowrap",
        zIndex: 0,
        letterSpacing: -2,
      }}
    >
      {text}
    </div>
  );
}
