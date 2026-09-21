import PostListWithActions from "../posts/PostListWithActions";
import type { AdminPostItem } from "./page";

/**
 * Las ENTRADAS (textos ya escritos, tabla `posts`) agrupadas por estado.
 *
 * Existe porque el panel solo pedía `pending_review` y pintaba esa cola AL FINAL
 * de la página, detrás de las propuestas descartadas: con 320 de estas delante,
 * las 13 entradas que esperaban decisión eran invisibles en la práctica. Y
 * `scheduled`, `rejected`, `approved` y `draft` no se veían en NINGUNA pantalla
 * —había 11 entradas programadas hasta diciembre que no se podían ni consultar
 * ni cancelar—. Aquí no se esconde ningún estado: lo que espera decisión va
 * abierto y arriba; el archivo, plegado.
 */

export function agruparPorEstado(
  posts: AdminPostItem[],
): Record<string, AdminPostItem[]> {
  // `reduce` y no `Object.groupBy`: eso es ES2024 y el tsconfig apunta a ES2022.
  return posts.reduce<Record<string, AdminPostItem[]>>((acc, p) => {
    (acc[p.status] ??= []).push(p);
    return acc;
  }, {});
}

export default function PostQueues({ posts }: { posts: AdminPostItem[] }) {
  const grupos = agruparPorEstado(posts);
  const pendientes = grupos.pending_review ?? [];
  const programadas = grupos.scheduled ?? [];
  const aprobadas = grupos.approved ?? [];
  const borradores = grupos.draft ?? [];
  const rechazadas = grupos.rejected ?? [];

  return (
    <div className="space-y-14">
      {/* ---------- Esperan decisión: SIEMPRE visible ---------- */}
      <section id="entradas-revision" className="scroll-mt-8">
        <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
          Entradas · esperan tu decisión · {pendientes.length}
        </h2>
        <p className="font-serif italic text-ink-dim text-sm mb-5">
          Textos ya escritos que un control detuvo antes de publicar (un dato sin
          confirmar, una cita en zona gris, el tema desviado), más los creados a
          mano. Nada de esto sale a la web hasta que tú lo digas.
        </p>
        {/* Sin condicional: cuando esté a cero hay que DECIRLO. Antes la sección
            desaparecía entera y lo único que se leía arriba era el «0» de las
            ideas, que es otra cola distinta — de ahí el «no veo nada». */}
        {pendientes.length === 0 ? (
          <p className="font-serif italic text-ink-faint">
            Nada esperando tu decisión. La cola está limpia.
          </p>
        ) : (
          <PostListWithActions items={pendientes} />
        )}
      </section>

      {/* ---------- Programadas ---------- */}
      {programadas.length > 0 && (
        <section id="entradas-programadas" className="scroll-mt-8">
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
            Entradas · programadas · {programadas.length}
          </h2>
          <p className="font-serif italic text-ink-dim text-sm mb-5">
            Saldrán solas al llegar su fecha. Desde aquí puedes desprogramarlas y
            devolverlas a la cola de decisión.
          </p>
          <PostListWithActions items={programadas} />
        </section>
      )}

      {/* ---------- Aprobadas sin fecha: el callejón sin salida ---------- */}
      {aprobadas.length > 0 && (
        <section id="entradas-aprobadas" className="scroll-mt-8">
          <details>
            <summary
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[3px] uppercase text-accent cursor-pointer"
            >
              Entradas · aprobadas sin fecha · {aprobadas.length}
            </summary>
            <p className="font-serif italic text-ink-dim text-sm mt-2 mb-5">
              Aquí caen las que despublicas. Ningún automatismo las recoge, así
              que se quedan quietas hasta que las publiques o las programes a
              mano: si no quieres que vuelvan a salir, déjalas aquí.
            </p>
            <PostListWithActions items={aprobadas} />
          </details>
        </section>
      )}

      {/* ---------- Borradores ---------- */}
      {borradores.length > 0 && (
        <section id="entradas-borradores" className="scroll-mt-8">
          <details>
            <summary
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint cursor-pointer"
            >
              Entradas · borradores · {borradores.length}
            </summary>
            <p className="font-serif italic text-ink-dim text-sm mt-2 mb-5">
              A medio hacer. Lo normal es que pasen solas a la cola de decisión;
              si llevan aquí mucho tiempo, es que algo se cortó por el camino.
            </p>
            <PostListWithActions items={borradores} />
          </details>
        </section>
      )}

      {/* ---------- Rechazadas: la papelera ---------- */}
      {rechazadas.length > 0 && (
        <section id="entradas-rechazadas" className="scroll-mt-8">
          <details>
            <summary
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint cursor-pointer"
            >
              Entradas · rechazadas · {rechazadas.length}
            </summary>
            <p className="font-serif italic text-ink-dim text-sm mt-2 mb-5">
              No se borran nunca: quedan aquí por si te arrepientes o quieres
              reescribirlas.
            </p>
            <PostListWithActions items={rechazadas} />
          </details>
        </section>
      )}
    </div>
  );
}
