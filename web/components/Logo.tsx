/**
 * Logo "Sol & Nube" · guiño al tatuaje de Robe sin copiar marcas.
 * Sol primitivo de rayos irregulares + nube ondulada a mano.
 * El delfín queda como ornamento decorativo aparte.
 */

// Redondea a 3 decimales. Necesario para que server y cliente
// produzcan el mismo string literal en SVG (de lo contrario, los
// floats con muchos decimales pueden diferir en el último bit y
// React lanza un hydration mismatch).
const r3 = (n: number) => Math.round(n * 1000) / 1000;

type SunMarkProps = {
  size?: number;
  color?: string;
  strokeWidth?: number;
  rays?: number;
};

export function SunMark({
  size = 40,
  color = "currentColor",
  strokeWidth = 1.6,
  rays = 12,
}: SunMarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 60 60" fill="none">
      <g
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        fill="none"
      >
        <circle cx="30" cy="30" r="7.5" />
        {Array.from({ length: rays }).map((_, i) => {
          const a = (i * Math.PI * 2) / rays;
          const r1 = 11 + (i % 2 === 0 ? 0 : 0.6);
          const r2 = 19 + (i % 3 === 0 ? 2 : i % 2 === 0 ? -1 : 1);
          return (
            <line
              key={i}
              x1={r3(30 + Math.cos(a) * r1)}
              y1={r3(30 + Math.sin(a) * r1)}
              x2={r3(30 + Math.cos(a) * r2)}
              y2={r3(30 + Math.sin(a) * r2)}
            />
          );
        })}
      </g>
    </svg>
  );
}

type LogoSunCloudProps = {
  name?: string;
  color?: string;
  scale?: number;
  stack?: boolean;
};

export function LogoSunCloud({
  name = "Entre Interiores",
  color = "currentColor",
  scale = 1,
  stack = false,
}: LogoSunCloudProps) {
  const Mark = (
    <svg
      width={56 * scale}
      height={44 * scale}
      viewBox="0 0 70 52"
      fill="none"
      aria-hidden
    >
      {/* sol */}
      <g
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        fill="none"
      >
        <circle cx="20" cy="20" r="5.5" />
        {Array.from({ length: 11 }).map((_, i) => {
          const a = (i * Math.PI * 2) / 11 - Math.PI / 2;
          const r1 = 8.5;
          const r2 = 13 + (i % 2 === 0 ? 1.2 : 0);
          return (
            <line
              key={i}
              x1={r3(20 + Math.cos(a) * r1)}
              y1={r3(20 + Math.sin(a) * r1)}
              x2={r3(20 + Math.cos(a) * r2)}
              y2={r3(20 + Math.sin(a) * r2)}
            />
          );
        })}
      </g>
      {/* nube */}
      <path
        d="M 30 38 Q 27 31 33 30 Q 35 25 41 27 Q 45 22 51 26 Q 60 25 60 32 Q 65 34 60 39 Q 53 43 44 41 Q 35 43 30 38 Z"
        stroke={color}
        strokeWidth="1.5"
        fill="none"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );

  const nameStyle: React.CSSProperties = {
    fontFamily: "var(--font-serif)",
    fontSize: (stack ? 22 : 26) * scale,
    fontWeight: 400,
    fontStyle: "italic",
    letterSpacing: stack ? 0.5 : 0.3,
    lineHeight: 1,
  };

  if (stack) {
    return (
      <span
        className="inline-flex flex-col items-center"
        style={{ gap: 8 * scale, color }}
      >
        {Mark}
        <span style={nameStyle}>{name}</span>
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center"
      style={{ gap: 14 * scale, color }}
    >
      {Mark}
      <span style={nameStyle}>{name}</span>
    </span>
  );
}

export function DolphinMark({
  size = 60,
  color = "currentColor",
}: {
  size?: number;
  color?: string;
}) {
  return (
    <svg
      width={size}
      height={size * 0.55}
      viewBox="0 0 100 55"
      fill="none"
      aria-hidden
    >
      <path
        d="M 8 30 Q 18 12 38 14 Q 50 14 62 22 Q 75 16 88 20 Q 82 26 78 26 Q 84 32 78 38 Q 70 42 58 38 Q 48 44 32 42 Q 18 40 8 30 Z M 22 28 L 18 22 L 26 26 Z"
        stroke={color}
        strokeWidth="1.4"
        fill="none"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx="32" cy="24" r="1" fill={color} />
    </svg>
  );
}
