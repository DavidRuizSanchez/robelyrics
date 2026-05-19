// Middleware de auth.
//
// Política Fase 2:
//   - Capa pública (/, /extremoduro/*, /robe/*, /blog/*, /legal/*): libre, indexable.
//   - Capa privada (/biblioteca/*): requiere token, redirige a /login si falta.
//   - Login/logout siempre libres.
//   - Assets (_next, favicon, album-covers, sitemap.xml, robots.txt, ads.txt): libres.
//
// El bloqueo "todo requiere auth salvo allowlist" del MVP queda atrás. Ahora
// solo /biblioteca/* requiere auth explícitamente.

import { NextResponse, type NextRequest } from "next/server";

const TOKEN_COOKIE = "robelyrics_token";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // /biblioteca/* requiere auth
  if (pathname.startsWith("/biblioteca")) {
    const token = req.cookies.get(TOKEN_COOKIE)?.value;
    if (!token) {
      const url = req.nextUrl.clone();
      url.pathname = "/login";
      url.searchParams.set("from", pathname);
      return NextResponse.redirect(url);
    }
  }

  // El noindex de las requests RSC (?_rsc= / cabecera RSC: 1) se gestiona en
  // next.config.mjs vía headers(): el middleware no es fiable para esto
  // porque Next.js sobreescribe las cabeceras del middleware en respuestas
  // text/x-component.

  return NextResponse.next();
}

export const config = {
  // Excluimos los assets estáticos para no atravesar el middleware en cada uno.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|album-covers|sitemap.xml|robots.txt|ads.txt).*)",
  ],
};
