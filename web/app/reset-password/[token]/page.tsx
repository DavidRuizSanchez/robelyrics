import LogoBomba from "@/components/LogoBomba";
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
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-10">
      <div className="mb-8 flex flex-col items-center gap-4">
        <LogoBomba size={200} priority />
        <p className="font-mono text-[10px] tracking-[4px] uppercase text-accent">
          Entre Interiores
        </p>
      </div>
      <ResetForm token={token} />
    </main>
  );
}
