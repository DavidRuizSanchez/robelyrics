import Header from "@/components/Header";
import PublicFooter from "@/components/PublicFooter";
import YoutubeFloatingPlayer from "@/components/YoutubeFloatingPlayer";
import { apiFetch } from "@/lib/api";
import { YoutubePlayerProvider } from "@/lib/youtube-player-context";
import type { AuthMe } from "@/lib/types";

// Layout de la capa privada (auth obligatoria por middleware).
// El middleware garantiza token, así que /auth/me debería responder. Si falla
// (sesión caducada en el momento exacto), tratamos como no admin y seguimos.
//
// Esta capa NO debe indexarse: añadimos la metadata robots correspondiente.
//
// Footer: usa el MISMO PublicFooter que la web pública (navegación completa
// Artistas/Discos/Explora/Sitio + newsletter), para que desde la zona privada
// se llegue a todas las secciones (desktop y móvil). El apoyo (Patreon/Ko-fi)
// vive en la home privada (/biblioteca) y en /biblioteca/donar.

export const metadata = {
  robots: { index: false, follow: false },
};

export default async function BibliotecaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  let isAdmin = false;
  try {
    const me = await apiFetch<AuthMe>("/auth/me");
    isAdmin = me.is_admin;
  } catch {
    isAdmin = false;
  }

  return (
    <YoutubePlayerProvider>
      <Header isAdmin={isAdmin} />
      {children}
      <YoutubeFloatingPlayer />
      <PublicFooter />
    </YoutubePlayerProvider>
  );
}
