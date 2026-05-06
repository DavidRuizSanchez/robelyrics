import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";
import ForgotForm from "./ForgotForm";

export const metadata = {
  title: "¿Olvidaste tu contraseña? · Entre Interiores",
  robots: { index: false, follow: false },
};

export default function ForgotPasswordPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="mb-10">
        <LogoSunCloud name="Entre Interiores" color={T.ink} scale={1.1} stack />
      </div>
      <ForgotForm />
    </main>
  );
}
