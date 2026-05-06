import LogoBomba from "@/components/LogoBomba";
import LoginForm from "./LoginForm";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string; error?: string }>;
}) {
  const { from = "/biblioteca", error } = await searchParams;

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-10">
      <div className="mb-8 flex flex-col items-center gap-4">
        <LogoBomba size={200} priority />
        <p className="font-mono text-[10px] tracking-[4px] uppercase text-accent">
          Entre Interiores
        </p>
      </div>

      <LoginForm from={from} error={error} />
    </main>
  );
}
