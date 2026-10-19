import { Inter } from "next/font/google";
import AdminNav from "./AdminNav";

// Texto de interfaz del admin en una sans legible. La variable y `font-ui` se
// aplican solo a este árbol: el Header de /biblioteca y la web pública siguen
// con su tipografía editorial.
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-admin",
  display: "swap",
});

// Layout común del panel admin: una sola barra de navegación compartida
// (antes estaba duplicada en cada página). No hace auth — cada página ya
// comprueba is_admin y redirige.
export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={`${inter.variable} font-ui text-[15px] leading-normal`}>
      <div className="px-5 md:px-14 pt-6 max-w-[1100px] mx-auto">
        <AdminNav />
      </div>
      {children}
    </div>
  );
}
