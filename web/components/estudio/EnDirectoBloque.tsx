import Link from "next/link";
import {
  ANCLA,
  ESTUDIO_PATH,
  SETLISTFM,
  coma,
  datoArtista,
  datoLugar,
  es,
  fechaLarga,
} from "./en-directo";

// Bloque «En directo» de las fichas de artista y de lugar. Las cifras salen del
// estudio del repertorio (`datos-por-pagina.ts`), no del cuerpo de la ficha: así
// no entran en la BD y no pueden desincronizarse del estudio.

const ORDINAL: Record<number, string> = { 1: "primera", 2: "segunda", 3: "tercera" };

function Marco({ children, ancla }: { children: React.ReactNode; ancla: string }) {
  return (
    <aside className="my-12 border border-divider px-5 py-5 md:px-7 md:py-6">
      <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
        En directo · datos propios
      </p>
      <div className="font-serif text-lg md:text-xl text-ink leading-relaxed space-y-3">
        {children}
      </div>
      <p className="mt-4 font-mono text-[10px] tracking-[1px] text-ink-faint">
        <Link
          href={`${ESTUDIO_PATH}#${ancla}`}
          data-cursor="hover"
          className="text-accent hover:underline"
        >
          El repertorio en directo de Extremoduro y Robe, en datos →
        </Link>
        <span className="block mt-1">
          Conciertos documentados en{" "}
          <a href="https://www.setlist.fm" className="hover:underline">
            setlist.fm
          </a>
          , archivo colaborativo: no son todos los que hubo.
        </span>
      </p>
    </aside>
  );
}

export function EnDirectoArtista({ slug }: { slug: string }) {
  const d = datoArtista(slug);
  if (!d) return null;
  const quien = slug === "robe" ? "Robe" : "Extremoduro";
  return (
    <Marco ancla={ANCLA.legado}>
      <p>
        De {quien} hay <strong>{es(d.setlists)} conciertos documentados</strong> entre {d.desde} y{" "}
        {d.hasta}, en {d.ciudades} ciudades
        {d.provincias === 50 ? " y las cincuenta provincias de España" : ` de ${d.provincias} provincias`}
        {d.fuera_de_espana > 0 ? `, más ${d.fuera_de_espana} fuera de España` : ""}.
      </p>
      <p>
        {slug === "robe" ? (
          <>
            El <strong>{coma(d.pct_ajeno)} %</strong> de lo que tocaba en directo no salía de sus
            cuatro discos.
          </>
        ) : (
          <>
            Solo el <strong>{coma(d.pct_ajeno)} %</strong> de lo que tocaba en directo no salía de
            sus propios discos.
          </>
        )}{" "}
        <a href={SETLISTFM[slug]} className="text-ink-dim hover:underline text-base">
          (setlist.fm)
        </a>
      </p>
    </Marco>
  );
}

export function EnDirectoLugar({ slug }: { slug: string }) {
  const d = datoLugar(slug);
  if (!d) return null;
  const primero = fechaLarga(d.primero);
  const ultimo = fechaLarga(d.ultimo);
  const reparto =
    d.extremoduro && d.robe
      ? ` (${d.extremoduro} de Extremoduro y ${d.robe} de Robe)`
      : d.robe
        ? " de Robe"
        : " de Extremoduro";

  if (d.tipo === "pais") {
    return (
      <Marco ancla={ANCLA.mapa}>
        <p>
          En {d.nombre} hay documentado{" "}
          {d.n === 1 ? <strong>un concierto</strong> : <strong>{d.n} conciertos</strong>}
          {reparto}
          {d.n === 1 && primero
            ? `, el ${primero}${d.primero_recinto ? ` en ${d.primero_recinto}` : ""}`
            : ""}
          .
        </p>
      </Marco>
    );
  }

  return (
    <Marco ancla={ANCLA.mapa}>
      <p>
        En {d.nombre} hay{" "}
        <strong>{d.n} conciertos documentados</strong>
        {reparto}
        {d.tipo === "region" ? `, en ${d.ciudades} localidades` : ""}
        {primero && ultimo && d.n > 1 ? `, del ${primero} al ${ultimo}` : ""}.
      </p>
      {d.es_el_primero && primero && (
        <p>
          Aquí está <strong>el primer concierto documentado</strong> de todos: el {primero}
          {d.primero_recinto && d.tipo === "ciudad" ? `, en ${d.primero_recinto}` : ""}.
        </p>
      )}
      {d.tipo === "ciudad" && d.provincia && d.provincia !== d.nombre && d.provincia_n > d.n && (
        <p>
          La provincia de {d.provincia} suma {d.provincia_n}
          {d.provincia_rank && d.provincia_rank <= 3
            ? `: la ${ORDINAL[d.provincia_rank]} de España`
            : ""}
          .
        </p>
      )}
      {d.tipo === "ciudad" && d.provincia === d.nombre && d.provincia_n > d.n && (
        <p>
          Con su provincia, {d.provincia_n}
          {d.provincia_rank && d.provincia_rank <= 3
            ? `: la ${ORDINAL[d.provincia_rank]} de España`
            : ""}
          .
        </p>
      )}
      {d.tipo === "region" && (
        <p>
          Por provincias:{" "}
          {Object.entries(d.provincias)
            .map(([p, n]) => `${p} ${n}`)
            .join(" y ")}
          .
        </p>
      )}
    </Marco>
  );
}
