import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";
import ResetForm from "./ResetForm";

export const metadata = {
  title: "Nueva contraseña · Entre Interiores",
  robots: { index: false, follow: false },
};

export default async function ResetPasswordPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="mb-10">
        <LogoSunCloud name="Entre Interiores" color={T.ink} scale={1.1} stack />
      </div>
      <ResetForm token={token} />
    </main>
  );
}
