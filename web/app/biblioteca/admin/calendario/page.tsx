import { redirect } from "next/navigation";

// El "Calendario" se fusionó en el panel unificado /biblioteca/admin/blog.
export default function AdminCalendarioRedirect() {
  redirect("/biblioteca/admin/blog");
}
