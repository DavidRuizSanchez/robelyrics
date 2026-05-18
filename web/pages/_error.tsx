// Página de error legacy minimalista. Pareja de `pages/_document.tsx`,
// existe solo para que `next build` no falle prerenderizando `/404` y `/500`
// con el `_error` default (que importa `<Html>` y rompe en App Router).
// La UX real de 404 vive en `app/not-found.tsx`.
import type { NextPageContext } from "next";

type Props = { statusCode: number };

function ErrorPage({ statusCode }: Props) {
  return (
    <div
      style={{
        fontFamily: "system-ui, sans-serif",
        padding: "4rem 1.5rem",
        textAlign: "center",
        background: "#0d0b0a",
        color: "#ede4d3",
        minHeight: "100vh",
      }}
    >
      <p style={{ letterSpacing: "0.3em", textTransform: "uppercase", color: "#a83a3a", fontSize: 12 }}>
        error {statusCode}
      </p>
      <h1 style={{ fontSize: 48, margin: "1rem 0 2rem", fontWeight: 400 }}>
        {statusCode === 404 ? "Página no encontrada" : "Algo ha fallado"}
      </h1>
      <a href="/" style={{ color: "#a83a3a", borderBottom: "1px solid #a83a3a", textDecoration: "none" }}>
        volver al inicio
      </a>
    </div>
  );
}

ErrorPage.getInitialProps = ({ res, err }: NextPageContext): Props => {
  const statusCode = res?.statusCode ?? err?.statusCode ?? 404;
  return { statusCode };
};

export default ErrorPage;
