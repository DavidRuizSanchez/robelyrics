import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";
import RegisterForm from "./RegisterForm";

export const metadata = {
  title: "Crear cuenta · Entre Interiores",
  description:
    "Regístrate gratis para acceder al cancionero íntimo: letras completas, karaoke sincronizado, interpretaciones fan y buscador semántico.",
};

export default function RegisterPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-10">
      <div className="mb-10">
        <LogoSunCloud
          name="Entre Interiores"
          color={T.ink}
          scale={1.1}
          stack
        />
      </div>
      <RegisterForm />
    </main>
  );
}
