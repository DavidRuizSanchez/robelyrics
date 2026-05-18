import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy del POST de suscripción al api interno. Evita exponer la URL del api
// al navegador y centraliza la auth/cookies en lib/api.

type SubscribeBody = {
  email?: string;
  source?: string;
};

type SubscribeResponse = {
  status: string;
  message: string;
};

export async function POST(request: Request) {
  let body: SubscribeBody;
  try {
    body = (await request.json()) as SubscribeBody;
  } catch {
    return NextResponse.json(
      { status: "invalid_email", message: "Email no válido." },
      { status: 400 },
    );
  }

  try {
    const data = await apiFetch<SubscribeResponse>(
      "/public/newsletter/subscribe",
      {
        method: "POST",
        body: { email: body.email, source: body.source },
        authenticated: false,
      },
    );
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json(
        { status: "error", message: "Reintenta en unos segundos." },
        { status: e.status },
      );
    }
    return NextResponse.json(
      { status: "error", message: "Error inesperado. Reintenta." },
      { status: 500 },
    );
  }
}
