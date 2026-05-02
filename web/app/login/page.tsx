import { loginAction } from "./actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string; error?: string }>;
}) {
  const { from = "/", error } = await searchParams;

  return (
    <main className="min-h-screen flex items-center justify-center px-6">
      <form
        action={loginAction}
        className="w-full max-w-sm space-y-5 bg-zinc-900 border border-zinc-800 rounded-xl p-8"
      >
        <h1 className="font-serif text-3xl font-bold text-center mb-2">
          RobeLyrics
        </h1>
        <p className="text-zinc-500 text-sm text-center mb-6">
          Acceso privado
        </p>

        <input type="hidden" name="from" value={from} />

        <div>
          <label className="block text-sm text-zinc-400 mb-1.5" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-zinc-100 focus:outline-none focus:border-zinc-600"
          />
        </div>

        <div>
          <label className="block text-sm text-zinc-400 mb-1.5" htmlFor="password">
            Contraseña
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-zinc-100 focus:outline-none focus:border-zinc-600"
          />
        </div>

        {error && (
          <p className="text-red-400 text-sm">{error}</p>
        )}

        <button
          type="submit"
          className="w-full bg-zinc-100 text-zinc-950 font-semibold rounded-md py-2 hover:bg-white transition"
        >
          Entrar
        </button>
      </form>
    </main>
  );
}
