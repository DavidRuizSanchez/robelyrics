"use client";

import { useEffect, useState } from "react";

// Pinta una variante u otra según la sesión, sin que el servidor tenga que
// leer la cookie. Las páginas públicas se sirven cacheadas y el HTML es el
// mismo para todos: sale la variante anónima y, si hay sesión, se cambia al
// hidratar. Googlebot y la gran mayoría de visitas son anónimas.

type Session = { logged_in: boolean; is_admin: boolean };

// Una sola petición por pantalla aunque haya varios ForSession. Caduca a los
// pocos segundos: el login es una server action con navegación en cliente, así
// que el módulo sobrevive y una sesión memorizada para siempre se quedaría en
// «acceder» después de entrar.
const TTL_MS = 5_000;
let pending: Promise<Session> | null = null;

function loadSession(): Promise<Session> {
  if (!pending) {
    pending = fetch("/sesion", { credentials: "same-origin", cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Session>) : null))
      .then((s) => s ?? { logged_in: false, is_admin: false })
      .catch(() => ({ logged_in: false, is_admin: false }));
    setTimeout(() => {
      pending = null;
    }, TTL_MS);
  }
  return pending;
}

export default function ForSession({
  anon,
  member,
  admin,
}: {
  anon?: React.ReactNode;
  member?: React.ReactNode;
  // Se añade a `member` cuando la cuenta es de admin.
  admin?: React.ReactNode;
}) {
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    let vivo = true;
    loadSession().then((s) => vivo && setSession(s));
    return () => {
      vivo = false;
    };
  }, []);

  if (!session?.logged_in) return <>{anon}</>;
  return (
    <>
      {session.is_admin && admin}
      {member}
    </>
  );
}
