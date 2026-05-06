import LogoBomba from "@/components/LogoBomba";
import ForgotForm from "./ForgotForm";

export const metadata = {
  title: "¿Olvidaste tu contraseña? · Entre Interiores",
  robots: { index: false, follow: false },
};

export default function ForgotPasswordPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-10">
      <div className="mb-8 flex flex-col items-center gap-4">
        <LogoBomba size={200} priority />
        <p className="font-mono text-[10px] tracking-[4px] uppercase text-accent">
          Entre Interiores
        </p>
      </div>
      <ForgotForm />
    </main>
  );
}
