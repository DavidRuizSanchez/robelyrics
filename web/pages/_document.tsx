// Legacy Pages Router _document.tsx requerido por el build de Next 15 para
// poder prerenderizar las páginas internas `/404` y `/500` de fallback.
// El sitio real vive en `app/` (App Router); este fichero existe únicamente
// para que `next build` no falle al instanciar Html fuera de _document.
import { Head, Html, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="es">
      <Head />
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
