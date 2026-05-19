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
  const { pathname, searchParams } = req.nextUrl;

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

  // Las requests de prefetch RSC (?_rsc=... o cabecera RSC: 1) son payloads
  // internos de Next.js App Router, no páginas navegables. Las bloqueamos
  // en robots.txt y, además, marcamos noindex aquí para sacar del índice
  // las que Google ya rastreó antes del fix.
  const isRscRequest =
    searchParams.has("_rsc") || req.headers.get("rsc") === "1";

  const res = NextResponse.next();
  if (isRscRequest) {
    res.headers.set("X-Robots-Tag", "noindex, nofollow");
  }
  return res;
}

export const config = {
  // Excluimos los assets estáticos para no atravesar el middleware en cada uno.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|album-covers|sitemap.xml|robots.txt|ads.txt).*)",
  ],
};
