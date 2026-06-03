import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy autenticado del consultorio "Pregúntale al viento". La cookie HttpOnly
// la añade apiFetch server-side; el navegador nunca ve la URL del api.

type AskBody = { question?: string };

type AskResponse = {
  question: string;
  answer: string;
  citations: { tipo: string; titulo: string; ref: string | null }[];
  grounded: boolean;
  kind: string;
  flagged: boolean;
};

export async function POST(request: Request) {
  let body: AskBody;
  try {
    body = (await request.json()) as AskBody;
  } catch {
    return NextResponse.json({ error: "Pregunta no válida." }, { status: 400 });
  }
  const question = (body.question || "").trim();
  if (question.length < 3) {
    return NextResponse.json({ error: "Escribe una pregunta." }, { status: 400 });
  }

  try {
    const data = await apiFetch<AskResponse>("/consult/ask", {
      method: "POST",
      body: { question },
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 401) {
        return NextResponse.json({ error: "Regístrate para preguntar." }, { status: 401 });
      }
      if (e.status === 429) {
        return NextResponse.json(
          { error: "Has preguntado mucho por hoy. Déjalo reposar y vuelve luego." },
          { status: 429 },
        );
      }
    }
    return NextResponse.json(
      { error: "El viento no responde ahora mismo. Reintenta en un momento." },
      { status: 500 },
    );
  }
}
