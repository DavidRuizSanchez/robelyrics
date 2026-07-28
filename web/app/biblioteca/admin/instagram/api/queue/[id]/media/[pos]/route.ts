import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { TOKEN_COOKIE } from "@/lib/api";

// GET → /admin/instagram/queue/{id}/media/{pos} : bytes de una pieza de media.
//
// No usa `apiFetch` porque la respuesta NO es JSON: son los bytes de una imagen
// o de un MP4. Se reenvía en streaming para no cargar el vídeo entero en
// memoria, y se propaga la cabecera Range para que el reproductor pueda saltar
// por el vídeo sin descargarlo del todo.
const API_BASE = process.env.API_INTERNAL_URL || "http://api:8000";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; pos: string }> },
) {
  const { id, pos } = await params;
  const numericId = Number(id);
  const numericPos = Number(pos);
  if (!Number.isFinite(numericId) || !Number.isFinite(numericPos)) {
    return NextResponse.json({ error: "parámetros no válidos" }, { status: 400 });
  }

  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "no autenticado" }, { status: 401 });
  }

  const rango = request.headers.get("range");
  const upstream = await fetch(
    `${API_BASE}/admin/instagram/queue/${numericId}/media/${numericPos}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        ...(rango ? { Range: rango } : {}),
      },
      redirect: "follow",
      cache: "no-store",
    },
  );

  if (!upstream.ok && upstream.status !== 206) {
    return NextResponse.json(
      { error: `media no disponible (${upstream.status})` },
      { status: upstream.status },
    );
  }

  const cabeceras = new Headers();
  for (const h of [
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
  ]) {
    const v = upstream.headers.get(h);
    if (v) cabeceras.set(h, v);
  }
  cabeceras.set("Cache-Control", "no-store");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: cabeceras,
  });
}
