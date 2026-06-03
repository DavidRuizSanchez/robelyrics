"use client";

import { useRef, useState } from "react";

type Turn = {
  question: string;
  answer: string;
  grounded: boolean;
};

export default function ConsultorioChat({
  suggestions,
}: {
  suggestions: string[];
}) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  async function ask(q: string) {
    const text = q.trim();
    if (text.length < 3 || pending) return;
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/biblioteca/consultorio/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "El viento no responde ahora mismo.");
      } else {
        setTurns((t) => [
          {
            question: text,
            answer: data.answer,
            grounded: !!data.grounded,
          },
          ...t,
        ]);
        setQuestion("");
      }
    } catch {
      setError("El viento no responde ahora mismo. Reintenta.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="relative"
      >
        <textarea
          ref={inputRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(question);
            }
          }}
          rows={3}
          maxLength={500}
          placeholder="Pregúntame lo que quieras…"
          disabled={pending}
          className="w-full resize-none bg-transparent border border-divider rounded-sm px-5 py-4 font-serif text-lg text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent/60 disabled:opacity-50"
        />
        <button
          type="submit"
          data-cursor="hover"
          disabled={pending || question.trim().length < 3}
          className="mt-3 font-mono text-[11px] tracking-[2.5px] uppercase border border-accent/60 text-accent hover:bg-accent hover:text-white px-5 py-2 transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-accent"
        >
          {pending ? "escuchando al viento…" : "preguntar"}
        </button>
      </form>

      {error && (
        <p className="mt-4 font-mono text-[12px] tracking-[1px] text-accent">{error}</p>
      )}

      {turns.length === 0 && !pending && (
        <div className="mt-8">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-3">
            por ejemplo
          </p>
          <ul className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  data-cursor="hover"
                  onClick={() => {
                    setQuestion(s);
                    inputRef.current?.focus();
                  }}
                  className="font-serif italic text-ink-dim hover:text-accent border border-divider hover:border-accent/50 rounded-full px-4 py-1.5 text-[15px] transition-colors"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-10 space-y-10">
        {turns.map((t, i) => (
          <article key={i} className="border-t border-divider pt-6">
            <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-3">
              le preguntaste
            </p>
            <p className="font-serif text-ink-dim text-lg mb-5">{t.question}</p>
            <div className="font-serif text-ink text-xl leading-relaxed whitespace-pre-line">
              {t.answer}
            </div>
            {!t.grounded && (
              <p className="mt-4 font-mono text-[10px] tracking-[1px] text-ink-faint italic">
                (de esto Robe no dejó dicho nada concreto: te responde a su manera,
                sin ponerle palabras que no fueran suyas)
              </p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
