import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renderiza el body_md del seo_content con estilo editorial Entre Interiores.
 * Aplicamos clases Tailwind a cada nodo via `components` para mantener la
 * paleta granate/serif del proyecto sin necesidad de plugin @tailwindcss/typography.
 */
export default function MarkdownArticle({ markdown }: { markdown: string }) {
  return (
    <div className="font-serif text-ink leading-[1.7] text-[18px] md:text-[19px] max-w-[680px]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="font-serif text-3xl md:text-4xl text-ink mt-10 mb-5 leading-[1.15] tracking-[-0.5px]">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="font-serif text-2xl md:text-[28px] text-ink mt-12 mb-4 leading-[1.2] tracking-[-0.3px]">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="font-serif text-xl md:text-[22px] text-ink mt-8 mb-3 italic">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="my-5 text-ink-dim leading-[1.75]">{children}</p>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              className="text-accent underline decoration-accent/40 hover:decoration-accent transition-colors"
              data-cursor="hover"
            >
              {children}
            </a>
          ),
          ul: ({ children }) => (
            <ul className="my-5 ml-6 list-disc space-y-2 text-ink-dim">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-5 ml-6 list-decimal space-y-2 text-ink-dim">{children}</ol>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-accent/60 pl-5 my-7 italic text-ink-dim">
              {children}
            </blockquote>
          ),
          em: ({ children }) => <em className="italic text-ink">{children}</em>,
          strong: ({ children }) => (
            <strong className="font-medium text-ink">{children}</strong>
          ),
          hr: () => <hr className="my-10 border-divider" />,
          code: ({ children }) => (
            <code className="font-mono text-[14px] text-accent bg-paper px-1.5 py-0.5">
              {children}
            </code>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
