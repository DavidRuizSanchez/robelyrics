/**
 * Imagen de cabecera de fondo opacada con máscara que se desvanece.
 * Capa decorativa absoluta detrás del hero. Server-friendly.
 */
export default function HeaderImageBackdrop({
  height = "1100px",
  src = "/imagen-cabecera-robe.jpg",
  opacity = 0.22,
  position = "center top",
  blur = 0,
}: {
  height?: string;
  src?: string;
  opacity?: number;
  position?: string;
  blur?: number;
}) {
  return (
    <>
      <div
        aria-hidden
        className="absolute top-0 left-0 right-0 pointer-events-none z-0"
        style={{
          height,
          backgroundImage: `url('${src}')`,
          backgroundSize: "cover",
          backgroundPosition: position,
          backgroundRepeat: "no-repeat",
          opacity,
          maskImage:
            "linear-gradient(180deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.7) 40%, rgba(0,0,0,0.3) 75%, transparent 100%)",
          WebkitMaskImage:
            "linear-gradient(180deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.7) 40%, rgba(0,0,0,0.3) 75%, transparent 100%)",
          filter: `saturate(0.85) contrast(1.05)${blur ? ` blur(${blur}px)` : ""}`,
        }}
      />
      <div
        aria-hidden
        className="absolute top-0 left-0 right-0 pointer-events-none z-0"
        style={{
          height,
          background:
            "radial-gradient(ellipse at 50% 0%, rgba(208,69,69,0.18) 0%, transparent 60%)",
          mixBlendMode: "overlay",
        }}
      />
    </>
  );
}
