import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import { AdminPage, EmptyState, StatusBadge, Table, cx, tdClass } from "@/components/admin/ui";

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
    <AdminPage
      title="Usuarios"
      intro={`Las ${users.length} cuentas registradas, de la más reciente a la más antigua.`}
    >
      {users.length === 0 ? (
        <EmptyState>No hay usuarios registrados todavía.</EmptyState>
      ) : (
        <Table head={["#", "Correo", "Rol", "Cuenta", "Correo verificado", "Alta"]}>
          {users.map((u) => (
            <tr key={u.id}>
              <td className={cx(tdClass, "font-mono text-ink-faint")}>{u.id}</td>
              <td className={cx(tdClass, "font-mono text-[13px] text-ink")}>{u.email}</td>
              <td className={tdClass}>
                {u.is_admin ? <StatusBadge tone="accent">Admin</StatusBadge> : <span className="text-ink-faint">Lector</span>}
              </td>
              <td className={tdClass}>
                {u.is_active ? <StatusBadge tone="ok">Activa</StatusBadge> : <StatusBadge tone="danger">Desactivada</StatusBadge>}
              </td>
              <td className={tdClass}>
                {u.email_verified ? <StatusBadge tone="ok">✓ Sí</StatusBadge> : <StatusBadge tone="warn">Pendiente</StatusBadge>}
              </td>
              <td className={cx(tdClass, "text-ink-dim whitespace-nowrap")}>
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
        </Table>
      )}
    </AdminPage>
  );
}
