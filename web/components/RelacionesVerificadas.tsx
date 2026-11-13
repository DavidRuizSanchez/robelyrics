// Relaciones verificadas de la ficha (`entity_relations`), pintadas desde el MISMO
// fragmento JSON-LD que se marca (`jsonld_verificadas`). Sin hooks: vale en server.
import Link from "next/link";

import { relacionesVisibles } from "@/lib/relaciones-jsonld";

export default function RelacionesVerificadas({
  relaciones,
  excluir = [],
}: {
  relaciones: Record<string, unknown> | null | undefined;
  excluir?: Iterable<string>;
}) {
  const filas = relacionesVisibles(relaciones, excluir);
  if (filas.length === 0) return null;
  const porEtiqueta = new Map<string, typeof filas>();
  for (const f of filas) porEtiqueta.set(f.etiqueta, [...(porEtiqueta.get(f.etiqueta) ?? []), f]);
  return (
    <section className="my-12 border border-divider">
      <table className="w-full border-collapse text-left">
        <caption className="caption-top px-5 py-3 font-mono text-[11px] tracking-[3px] uppercase text-accent border-b border-divider text-left">
          Relaciones
        </caption>
        <tbody>
          {[...porEtiqueta.entries()].map(([etiqueta, items]) => (
            <tr key={etiqueta} className="border-b border-divider last:border-b-0">
              <th
                scope="row"
                className="align-top w-[40%] md:w-[28%] px-5 py-4 font-mono text-[10px] md:text-[11px] tracking-[2px] uppercase text-ink-faint font-normal"
              >
                {etiqueta}
              </th>
              <td className="align-top px-5 py-4 font-serif text-lg text-ink leading-relaxed">
                <ul className="space-y-1">
                  {items.map((f) => (
                    <li key={`${f.nombre}-${f.detalle ?? ""}`}>
                      {f.href ? (
                        <Link href={f.href} data-cursor="hover" className="text-accent hover:underline">
                          {f.nombre}
                        </Link>
                      ) : (
                        f.nombre
                      )}
                      {f.detalle && <span className="text-ink-dim"> · {f.detalle}</span>}
                    </li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
