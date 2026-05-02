import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";
import { loginAction } from "./actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string; error?: string }>;
}) {
  const { from = "/", error } = await searchParams;

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

      <form
        action={loginAction}
        className="w-full max-w-sm space-y-6 border border-divider bg-paper/30 p-8"
      >
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent text-center">
          acceso privado
        </p>

        <input type="hidden" name="from" value={from} />

        <div>
          <label
            className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
            htmlFor="email"
          >
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif italic text-lg text-ink"
          />
        </div>

        <div>
          <label
            className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
            htmlFor="password"
          >
            Contraseña
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif italic text-lg text-ink"
          />
        </div>

        {error && (
          <p className="text-accent text-sm font-mono tracking-[1px]">
            {error}
          </p>
        )}

        <button
          type="submit"
          data-cursor="hover"
          className="w-full border border-accent text-accent hover:bg-accent hover:text-white font-mono text-[11px] tracking-[3px] uppercase py-3 transition-colors"
        >
          entrar
        </button>
      </form>
    </main>
  );
}
