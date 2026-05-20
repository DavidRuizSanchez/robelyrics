import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";

type UserListItem = {
  id: number;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
};

export const metadata = {
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function AdminUsersPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/users");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let users: UserListItem[] = [];
  try {
    users = await apiFetch<UserListItem[]>("/admin/users");
  } catch {
    users = [];
  }

  return (
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-5xl mx-auto">
      <header className="mb-12">
        <div className="flex items-center justify-between mb-2">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
            panel admin
          </p>
          <nav className="font-mono text-[10px] tracking-[2px] uppercase flex gap-4">
            <Link
              href="/biblioteca/admin/sources"
              data-cursor="hover"
              className="text-ink-dim hover:text-accent"
            >
              fuentes
            </Link>
            <Link
              href="/biblioteca/admin/seo"
              data-cursor="hover"
              className="text-ink-dim hover:text-accent"
            >
              SEO content
            </Link>
            <span className="text-accent">usuarios</span>
            <Link
              href="/biblioteca/admin/subscribers"
              data-cursor="hover"
              className="text-ink-dim hover:text-accent"
            >
              suscriptores
            </Link>
          </nav>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl text-ink mb-3">
          Usuarios registrados
        </h1>
        <p className="font-serif italic text-ink-dim text-lg max-w-2xl">
          Vista de los {users.length} usuario{users.length === 1 ? "" : "s"}{" "}
          de Entre Interiores. Orden cronológico inverso (los más recientes
          primero).
        </p>
      </header>

      {users.length === 0 ? (
        <p className="font-serif italic text-ink-faint">
          No hay usuarios registrados todavía.
        </p>
      ) : (
        <div className="overflow-x-auto border border-divider">
          <table className="w-full text-left">
            <thead className="bg-paper">
              <tr className="font-mono text-[10px] tracking-[2px] uppercase text-ink-dim">
                <th className="px-4 py-3">id</th>
                <th className="px-4 py-3">email</th>
                <th className="px-4 py-3 text-center">admin</th>
                <th className="px-4 py-3 text-center">activo</th>
                <th className="px-4 py-3 text-center">verificado</th>
                <th className="px-4 py-3">creado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-divider">
              {users.map((u) => (
                <tr key={u.id} className="font-serif text-ink">
                  <td className="px-4 py-3 font-mono text-[12px] text-ink-dim">
                    {u.id}
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-[13px]">{u.email}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <Badge yes={u.is_admin} on="ADMIN" off="·" />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <Badge yes={u.is_active} on="OK" off="OFF" />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <Badge yes={u.email_verified} on="✓" off="pendiente" />
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-ink-faint">
                    {new Date(u.created_at).toLocaleString("es-ES", {
                      timeZone: "Europe/Madrid",
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function Badge({
  yes,
  on,
  off,
}: {
  yes: boolean;
  on: string;
  off: string;
}) {
  return yes ? (
    <span className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
      {on}
    </span>
  ) : (
    <span className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
      {off}
    </span>
  );
}
