import LogoBomba from "@/components/LogoBomba";
import RegisterForm from "./RegisterForm";

export const metadata = {
  title: "Crear cuenta · Entre Interiores",
  description:
    "Regístrate gratis para acceder al cancionero íntimo: letras completas, karaoke sincronizado, interpretaciones fan y buscador semántico.",
};

export default function RegisterPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-10">
      <div className="mb-8 flex flex-col items-center gap-4">
        <LogoBomba size={200} priority />
        <p className="font-mono text-[10px] tracking-[4px] uppercase text-accent">
          Entre Interiores
        </p>
      </div>
      <RegisterForm />
    </main>
  );
}
