import { redirect } from "next/navigation";

// El antiguo "Diario" se fusionó en el panel unificado /biblioteca/admin/blog.
export default function AdminPostsRedirect() {
  redirect("/biblioteca/admin/blog");
}
