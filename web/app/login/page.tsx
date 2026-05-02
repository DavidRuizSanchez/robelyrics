import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";
import LoginForm from "./LoginForm";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string; error?: string }>;
}) {
  const { from = "/biblioteca", error } = await searchParams;

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="mb-10">
        <LogoSunCloud
          name="Entre Interiores"
          color={T.ink}
          scale={1.1}
          stack
        />
      </div>

      <LoginForm from={from} error={error} />
    </main>
  );
}
