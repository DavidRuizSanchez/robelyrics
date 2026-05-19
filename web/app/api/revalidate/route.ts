import { NextResponse } from "next/server";
import { revalidatePath, revalidateTag } from "next/cache";

// Endpoint interno para invalidar la caché de Next.js cuando el backend
// publica un post nuevo. Se autentica con un token estático compartido
// (REVALIDATE_TOKEN) inyectado tanto en el container `web` como en `api`.
//
// El backend lo llama desde `app.services.publishing._revalidate_next` tras
// auto_publish_post. Cuerpo esperado:
//   { paths?: string[], tags?: string[] }
// El header X-Revalidate-Token debe coincidir con REVALIDATE_TOKEN.

type RevalidateBody = {
  paths?: string[];
  tags?: string[];
};

export async function POST(request: Request) {
  const expected = process.env.REVALIDATE_TOKEN;
  if (!expected) {
    return NextResponse.json(
      { ok: false, error: "REVALIDATE_TOKEN no configurado en el servidor" },
      { status: 500 },
    );
  }

  const got = request.headers.get("X-Revalidate-Token");
  if (got !== expected) {
    return NextResponse.json({ ok: false, error: "Token inválido" }, { status: 401 });
  }

  let body: RevalidateBody;
  try {
    body = (await request.json()) as RevalidateBody;
  } catch {
    return NextResponse.json({ ok: false, error: "JSON inválido" }, { status: 400 });
  }

  const paths = Array.isArray(body.paths) ? body.paths : [];
  const tags = Array.isArray(body.tags) ? body.tags : [];

  for (const p of paths) {
    if (typeof p === "string" && p.startsWith("/")) {
      revalidatePath(p);
    }
  }
  for (const t of tags) {
    if (typeof t === "string" && t.length > 0) {
      revalidateTag(t);
    }
  }

  return NextResponse.json({ ok: true, paths, tags });
}
