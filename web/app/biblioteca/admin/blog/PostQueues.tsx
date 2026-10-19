import { Details, EmptyState, Section } from "@/components/admin/ui";
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
    <div className="space-y-10">
      {/* Sin condicional: cuando esté a cero hay que DECIRLO. Antes la sección
          desaparecía entera y lo único que se leía arriba era el «0» de las
          ideas, que es otra cola distinta — de ahí el «no veo nada». */}
      <Section
        id="entradas-revision"
        title="Entradas que esperan tu decisión"
        count={pendientes.length}
        help="Textos ya escritos que un control frenó antes de publicar (un dato sin confirmar, una cita dudosa, el tema desviado), más los creados a mano. Nada sale a la web hasta que tú lo digas."
      >
        {pendientes.length === 0 ? (
          <EmptyState>Nada esperando tu decisión. La cola está limpia.</EmptyState>
        ) : (
          <PostListWithActions items={pendientes} />
        )}
      </Section>

      {programadas.length > 0 && (
        <Section
          id="entradas-programadas"
          title="Entradas programadas"
          count={programadas.length}
          help="Saldrán solas al llegar su fecha. Si las desprogramas vuelven a la cola de decisión."
        >
          <PostListWithActions items={programadas} />
        </Section>
      )}

      {aprobadas.length > 0 && (
        <Plegada
          id="entradas-aprobadas"
          titulo="Entradas aprobadas sin fecha"
          n={aprobadas.length}
          ayuda="Aquí caen las que despublicas. Ningún automatismo las recoge: se quedan quietas hasta que las publiques o las programes a mano."
        >
          <PostListWithActions items={aprobadas} />
        </Plegada>
      )}

      {borradores.length > 0 && (
        <Plegada
          id="entradas-borradores"
          titulo="Borradores"
          n={borradores.length}
          ayuda="A medio hacer. Lo normal es que pasen solos a la cola de decisión; si llevan aquí mucho tiempo, algo se cortó por el camino."
        >
          <PostListWithActions items={borradores} />
        </Plegada>
      )}

      {rechazadas.length > 0 && (
        <Plegada
          id="entradas-rechazadas"
          titulo="Entradas rechazadas"
          n={rechazadas.length}
          ayuda="No se borran nunca: quedan aquí por si te arrepientes o quieres reescribirlas."
        >
          <PostListWithActions items={rechazadas} />
        </Plegada>
      )}
    </div>
  );
}

function Plegada({
  id,
  titulo,
  n,
  ayuda,
  children,
}: {
  id: string;
  titulo: string;
  n: number;
  ayuda: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-28">
      <Details
        summary={
          <span className="text-base text-ink-dim">
            {titulo} <span className="font-mono text-ink-faint">{n}</span>
          </span>
        }
      >
        <p className="mb-3 text-sm text-ink-faint">{ayuda}</p>
        {children}
      </Details>
    </section>
  );
}
