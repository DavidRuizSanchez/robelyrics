import AdminNav from "./AdminNav";

// Layout común del panel admin: una sola barra de navegación compartida
// (antes estaba duplicada en cada página). No hace auth — cada página ya
// comprueba is_admin y redirige.
export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="px-5 md:px-14 pt-6 max-w-[1100px] mx-auto">
        <AdminNav />
      </div>
      {children}
    </div>
  );
}
