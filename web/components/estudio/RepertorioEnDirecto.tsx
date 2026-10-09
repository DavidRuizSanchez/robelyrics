"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import s from "./estudio.module.css";
import {
  ANIOS_E,
  ANIOS_R,
  ATRAS,
  CIUDADES,
  DISCO_E,
  DISCO_R,
  DUMB,
  ONCE,
  PROV,
  RECINTOS,
  TOP,
  type FilaDisco,
} from "./datos-repertorio";
import { MAPA_INSET, MAPA_PATHS } from "./mapa-provincias";

const POST = "/blog/canciones-extremoduro-sin-registro-en-directo";

const es = (n: number) => n.toLocaleString("es-ES");
const coma = (n: number | string) => String(n).replace(".", ",");

/* Rampa secuencial de un solo tono, y escala de raíz cuadrada: en lineal los 48
   conciertos de Madrid aplastan a las treinta provincias que están entre 1 y 10
   y el mapa sale casi entero del mismo color. */
const RAMPA = ["#3a1a18", "#5c2320", "#7d2c2a", "#9c3634", "#b8443f", "#cf5f55"];
const MAX_PROV = Math.max(...Object.values(PROV).map((p) => p.n));
const colorProv = (n: number) =>
  RAMPA[Math.min(RAMPA.length - 1, Math.floor(Math.sqrt(n / MAX_PROV) * RAMPA.length))];

// --------------------------------------------------------------------------- //
// Barras
// --------------------------------------------------------------------------- //

function BarraApilada({
  titulo,
  meta,
  valor,
  tip,
  anchoE,
  anchoR,
}: {
  titulo: string;
  meta?: string;
  valor: React.ReactNode;
  tip: string;
  anchoE: number;
  anchoR?: number;
}) {
  return (
    <div className={s.fila}>
      <div className={s.filaTop}>
        <div className={s.filaTit}>
          {titulo}
          {meta ? <em>{meta}</em> : null}
        </div>
        <div className={`${s.filaVal} ${s.num}`}>{valor}</div>
      </div>
      <div className={s.pista} title={tip}>
        {anchoE > 0 && (
          <div className={`${s.seg} ${s.segE}`} style={{ width: `${anchoE}%` }} />
        )}
        {anchoR ? (
          <div className={`${s.seg} ${s.segR}`} style={{ width: `${anchoR}%` }} />
        ) : null}
      </div>
    </div>
  );
}

function BarrasDisco({ filas, max, serie }: { filas: FilaDisco[]; max: number; serie: "e" | "r" }) {
  return (
    <div className={s.barras}>
      {filas.map(([nombre, total, pct]) => (
        <div className={s.fila} key={nombre}>
          <div className={s.filaTop}>
            <div className={s.filaTit} style={{ fontSize: "15.5px" }}>
              {nombre}
            </div>
            <div className={`${s.filaVal} ${s.num}`}>
              {es(total)} <span>· {coma(pct)} %</span>
            </div>
          </div>
          <div
            className={s.pista}
            title={`${nombre}: ${total} interpretaciones, el ${coma(pct)} % del total`}
          >
            <div
              className={`${s.seg} ${serie === "e" ? s.segE : s.segR}`}
              style={{ width: `${(total / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Las once: se pinchan para ver el verso y se marcan las escuchadas.
// El marcador es el motivo de la pieza: casi nadie llega a once, y enterarse de
// eso es lo que hace que a uno le apetezca contarlo.
// --------------------------------------------------------------------------- //

function LasOnce() {
  const [abiertas, setAbiertas] = useState<Set<number>>(new Set());
  const [oidas, setOidas] = useState<Set<number>>(new Set());

  const alterna = (set: Set<number>, i: number) => {
    const copia = new Set(set);
    if (copia.has(i)) copia.delete(i);
    else copia.add(i);
    return copia;
  };

  const n = oidas.size;
  const cola =
    n === 0
      ? "Empieza por la que más te suene."
      : n === 11
        ? "Las once. Eres de los nuestros."
        : n >= 8
          ? "Casi todas. Pocas personas llegan ahí."
          : n >= 4
            ? "Más de la media."
            : "Hay disco por delante.";

  return (
    <>
      <div className={s.once}>
        {ONCE.map(([titulo, meta, verso], i) => {
          const abierta = abiertas.has(i);
          return (
            <div
              key={titulo}
              className={`${s.card}${i === 9 ? ` ${s.cardDestaca}` : ""}`}
            >
              <div>
                <button
                  type="button"
                  className={`${s.cardBoton} ${s.cardT}`}
                  aria-expanded={abierta}
                  onClick={() => setAbiertas((p) => alterna(p, i))}
                >
                  {titulo}
                </button>
                {abierta ? (
                  <div className={s.verso}>«{verso}»</div>
                ) : (
                  <div className={s.pistaCard}>toca para leer un verso</div>
                )}
              </div>
              <div>
                <div className={s.cardM}>{meta}</div>
                <label className={s.oida}>
                  <input
                    type="checkbox"
                    checked={oidas.has(i)}
                    onChange={() => setOidas((p) => alterna(p, i))}
                  />
                  la he escuchado
                </label>
              </div>
            </div>
          );
        })}
      </div>
      <div className={s.marcador} aria-live="polite">
        Has escuchado <b className={s.num}>{n}</b> de 11. {cola}
      </div>
    </>
  );
}

// --------------------------------------------------------------------------- //
// Mapa de provincias
// --------------------------------------------------------------------------- //

function Mapa() {
  const svgRef = useRef<SVGSVGElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [activa, setActiva] = useState<string | null>(null);
  const [fijada, setFijada] = useState<string | null>(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });

  const coloca = useCallback((ev: { clientX: number; clientY: number }) => {
    const svg = svgRef.current;
    const tip = tipRef.current;
    if (!svg || !tip) return;
    const r = svg.getBoundingClientRect();
    const x = ev.clientX - r.left;
    const y = ev.clientY - r.top;
    setPos({
      x: Math.max(4, Math.min(x + 16, r.width - tip.offsetWidth - 8)),
      y: Math.max(4, y - tip.offsetHeight - 10),
    });
  }, []);

  const nombre = fijada ?? activa;
  const info = nombre ? PROV[nombre] : undefined;
  const restantes = info ? info.n_ciudades - info.ciudades.length : 0;

  return (
    <>
      <div className={s.mapaCaja}>
        <svg
          ref={svgRef}
          className={s.mapa}
          viewBox="0 0 1000 720"
          role="img"
          aria-label="Mapa de España por provincias con los conciertos documentados de cada una"
          onMouseMove={(e) => {
            const prov = (e.target as Element).closest("path")?.getAttribute("data-prov");
            if (prov && !fijada) {
              setActiva(prov);
              coloca(e);
            }
          }}
          onMouseLeave={() => {
            if (!fijada) setActiva(null);
          }}
          // Un clic la fija: en el móvil no hay hover, y además deja leerla con calma.
          onClick={(e) => {
            const prov = (e.target as Element).closest("path")?.getAttribute("data-prov");
            if (!prov) return;
            if (fijada === prov) {
              setFijada(null);
              setActiva(null);
              return;
            }
            setFijada(prov);
            setActiva(prov);
            coloca(e);
          }}
        >
          <rect
            className={s.insetCaja}
            x={MAPA_INSET.x}
            y={MAPA_INSET.y}
            width={MAPA_INSET.w}
            height={MAPA_INSET.h}
          />
          {Object.entries(MAPA_PATHS).map(([prov, d]) => {
            const p = PROV[prov];
            return (
              <path
                key={prov}
                d={d}
                data-prov={prov}
                className={fijada === prov ? s.sel : undefined}
                fill={p ? colorProv(p.n) : "rgba(237,228,211,.07)"}
              >
                {/* `title` nativo: el dato sigue estando sin JS y para un lector de pantalla. */}
                <title>{p ? `${prov}: ${p.n} conciertos` : prov}</title>
              </path>
            );
          })}
        </svg>
        <div
          ref={tipRef}
          className={`${s.tip}${info ? ` ${s.tipOn}` : ""}`}
          style={{ left: pos.x, top: pos.y }}
        >
          {info && nombre ? (
            <>
              <b>{nombre}</b>
              <span className={`${s.num} ${s.tipN}`}>{info.n}</span>
              <div className={s.tipD}>
                conciertos · {info.n_ciudades} ciudad{info.n_ciudades > 1 ? "es" : ""}
                <br />
                de {info.primer} a {info.ultimo}
                <br />
                {info.ciudades.map((c) => `${c.c} ${c.n}`).join(" · ")}
                {restantes > 0 ? ` · y ${restantes} más` : ""}
              </div>
            </>
          ) : null}
        </div>
      </div>
      <div className={s.leyendaMapa}>
        <span>1 concierto</span>
        <i style={{ background: `linear-gradient(90deg, ${RAMPA.join(",")})` }} />
        <span>48</span>
        <span style={{ marginLeft: 16 }}>recuadro: Canarias</span>
      </div>
    </>
  );
}

// --------------------------------------------------------------------------- //
// Ranking: provincia o ciudad
// --------------------------------------------------------------------------- //

function Ranking() {
  const [porProvincia, setPorProvincia] = useState(true);

  const filas = useMemo(() => {
    if (porProvincia) {
      return Object.entries(PROV)
        .map(([n, v]): [string, string, number] => [
          n,
          `${v.n_ciudades} ciudad${v.n_ciudades > 1 ? "es" : ""}`,
          v.n,
        ])
        .sort((a, b) => b[2] - a[2])
        .slice(0, 15);
    }
    return CIUDADES.map((c): [string, string, number] => [c[0], "conciertos", c[2]]);
  }, [porProvincia]);

  const max = filas[0][2];

  return (
    <>
      <div className={s.tabs} role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={porProvincia}
          onClick={() => setPorProvincia(true)}
        >
          Por provincia
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={!porProvincia}
          onClick={() => setPorProvincia(false)}
        >
          Por ciudad
        </button>
      </div>
      <div className={s.barras}>
        {filas.map(([nombre, meta, n]) => (
          <BarraApilada
            key={nombre}
            titulo={nombre}
            meta={meta}
            valor={es(n)}
            tip={`${nombre}: ${n} conciertos documentados`}
            anchoE={(n / max) * 100}
          />
        ))}
      </div>
    </>
  );
}

// --------------------------------------------------------------------------- //
// La página
// --------------------------------------------------------------------------- //

export default function RepertorioEnDirecto() {
  return (
    <div className={s.estudio}>
      <header>
        <p className={s.eyebrow}>Estudio del repertorio en directo · Entre Interiores</p>
        <h1>Las 11 canciones de Extremoduro que nunca has escuchado en directo</h1>
        <p className={`${s.lede} ${s.col}`}>
          Extremoduro y Robe dejaron <strong>591 conciertos</strong> documentados entre 1987 y
          2024. Cruzando ese repertorio con las 132 composiciones del catálogo aparecen once
          canciones de las que <strong>no existe un solo registro</strong>: ni en los setlists, ni
          en las grabaciones que circulan, ni en los años que lleva la gente reconstruyendo esta
          historia. Una de ellas repite doce veces un verso que nadie ha podido documentar cantado.
        </p>

        <div className={s.kpis}>
          <div className={s.kpi}>
            <b className={s.num}>591</b>
            <span>Conciertos documentados</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>5.581</b>
            <span>Interpretaciones contadas</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>132</b>
            <span>Composiciones del catálogo</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>11</b>
            <span>Sin registro en directo</span>
          </div>
        </div>
      </header>

      <section>
        <h3>La pieza</h3>
        <h2 className={s.col}>El concierto que nunca fue</h2>
        <p className={`${s.col} ${s.dim}`}>
          Las once, puestas en el papel que se pega al suelo del escenario y que al acabar alguien
          se lleva de recuerdo. Van en orden de publicación, que es el único orden que nos consta:
          nadie decidió nunca en qué orden sonarían.
        </p>
      </section>

      <div className={s.escenario}>
        <div className={s.setlist}>
          <div className={s.slCab}>
            <b>
              El concierto
              <br />
              que nunca fue
            </b>
            <span>Once canciones · sin registro en directo</span>
          </div>
          <ol className={s.slTemas}>
            {ONCE.map(([titulo, meta]) => (
              <li key={titulo}>
                <span className={s.slTema}>{titulo}</span>
                <span className={s.slAnyo}>’{meta.slice(-2)}</span>
              </li>
            ))}
          </ol>
          <div className={s.slPie}>
            no consta que ninguna
            <br />
            llegara a sonar
          </div>
          <div className={s.slSello}>Entre Interiores · entreinteriores.com</div>
        </div>
      </div>

      <section id="once" className={s.ancla}>
        <h3>El hallazgo</h3>
        <h2 className={s.col}>Once canciones de las que nadie guarda registro</h2>
        <p className={`${s.col} ${s.dim}`}>
          De las 132 composiciones publicadas en disco de estudio o EP, once no aparecen en ningún
          setlist documentado. Cada una está verificada como corte real de su disco contra
          MusicBrainz, con su posición en el tracklist.
        </p>
        <p className={`${s.col} ${s.dim}`}>
          <strong>No es lo mismo que decir que no sonaron nunca.</strong> Un archivo de conciertos
          lo rellenan personas, y lo que nadie apuntó no existe en él. Lo que sí se puede afirmar
          es que dos búsquedas independientes llegaron casi a la misma lista: la nuestra, cruzando
          591 setlists con el catálogo, y la de{" "}
          <a href="https://www.youtube.com/watch?v=fbAKGSeQGy4">Juancares</a>, que lleva años
          reconstruyendo la historia en directo de la banda y nombró{" "}
          <strong>diez de estas once</strong> en dos programas de su consultorio sin conocer este
          estudio. La única que no aparece en sus listas es «Manué IV».
        </p>

        <LasOnce />

        <div className={`${s.nota} ${s.col}`}>
          «Luce la oscuridad» se repite <strong>doce veces</strong> dentro de su canción,
          repartidas de principio a fin. Es uno de los estribillos más insistentes del catálogo, y
          no consta que se cantara nunca delante de nadie.
        </div>

        <h3 className={s.conMargen}>Por qué nos fiamos de la ausencia</h3>
        <p className={`${s.col} ${s.dim}`}>
          Una lista de lo que falta solo vale si el archivo es capaz de registrar lo raro. Lo es:
          tres canciones que sonaron <strong>una única vez</strong> («¡Qué sonrisa tan rara!» y
          «Tomás» en una prueba en la sala Neptuno de Granada antes de publicar <em>Agila</em>, y
          «Te juzgarán sólo por tus errores» en la presentación de <em>Pedrá</em> en Madrid, 1995)
          aparecen en setlist.fm con exactamente un toque cada una. Las fechas las cuenta
          Juancares; el recuento sale del archivo. Dos fuentes que no se hablan, coincidiendo en
          actuaciones únicas de hace treinta años.
        </p>
        <p className={`${s.col} ${s.dim}`}>
          Y donde no coinciden, también se dice: de «Sin Dios Ni Amo» hubo{" "}
          <strong>un setlist publicado en la revista Heavy Rock</strong> en el que sí figuraba,
          pero en las cintas grabadas en conciertos de aquella época no aparece. Es la única de las
          once con una prueba a favor, y es de papel.
        </p>

        <div className={`${s.nota} ${s.col}`}>
          ¿Tienes una grabación, una entrada, una foto del setlist pegado al escenario? Cualquiera
          de estas once se cae de la lista con una sola prueba, y eso sería la mejor noticia que
          puede dar este estudio. Escríbenos.
        </div>

        <p className={`${s.col} ${s.dim}`}>
          El relato de las once, una por una y con su letra delante, está en{" "}
          <Link href={POST}>
            Once canciones de Extremoduro que nunca sonaron en directo
          </Link>
          .
        </p>
      </section>

      <section id="mapa" className={s.ancla}>
        <h3>El mapa</h3>
        <h2 className={s.col}>Tocaron en las cincuenta provincias de España</h2>
        <p className={`${s.col} ${s.dim}`}>
          Los 591 conciertos documentados tienen fecha y, 568 de ellos, ciudad:{" "}
          <strong>193 ciudades distintas</strong>, y en <strong>106 de ellas una sola vez</strong>.
          Agrupadas por provincia, no falta ninguna.
        </p>
        <p className={`${s.col} ${s.dim}`}>
          Pasa el ratón por encima, o toca si estás en el móvil. Cada provincia trae sus
          conciertos, en cuántas ciudades distintas y entre qué años.
        </p>

        <Mapa />

        <div className={`${s.nota} ${s.col}`}>
          La segunda provincia donde más veces tocaron es <strong>Cáceres, con 37</strong>, por
          delante de Barcelona. Solo Madrid está por encima. Y toda la aventura americana cabe en{" "}
          <strong>nueve conciertos</strong>: cuatro en Argentina, dos en Uruguay y uno en Colombia,
          Ecuador y Chile.
        </div>

        <div className={s.kpis} style={{ marginTop: 28 }}>
          <div className={s.kpi}>
            <b className={s.num}>50</b>
            <span>Provincias, de 50</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>193</b>
            <span>Ciudades distintas</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>106</b>
            <span>Ciudades de un solo concierto</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>9</b>
            <span>Conciertos fuera de España</span>
          </div>
        </div>

        <h3 className={s.conMargen}>El ranking</h3>
        <Ranking />

        <div className={`${s.nota} ${s.col}`}>
          El corte por ciudad reparte lo que en realidad está junto: Madrid aparece con 34 y su
          área suma otros 14 en Leganés, Rivas, Alcalá, Pozuelo y Móstoles. Por eso el mapa va por
          provincia.
        </div>

        <h3 className={s.conMargen}>Los recintos</h3>
        <p className={`${s.col} ${s.dim}`}>
          Los nombres genéricos van con su ciudad entre paréntesis: «Plaza de Toros» a secas no
          identifica un sitio, identifica dieciséis sitios distintos.
        </p>
        <div className={s.barras}>
          {RECINTOS.map(([recinto, ciudad, n]) => (
            <BarraApilada
              key={`${recinto}-${ciudad}`}
              titulo={recinto}
              meta={ciudad}
              valor={es(n)}
              tip={`${recinto}: ${n} conciertos documentados`}
              anchoE={(n / 8) * 100}
            />
          ))}
        </div>
      </section>

      <section id="mas-tocadas" className={s.ancla}>
        <h3>Lo más tocado</h3>
        <h2 className={s.col}>Doce canciones, mil seiscientas noches</h2>
        <p className={`${s.col} ${s.dim}`}>
          Suma de las veces que cada canción aparece en un setlist, repartida entre las dos
          formaciones.
        </p>

        <div className={s.leyenda}>
          <span>
            <i style={{ background: "var(--granate)" }} />
            Extremoduro · 459 conciertos
          </span>
          <span>
            <i style={{ background: "var(--ocre)" }} />
            Robe · 132 conciertos
          </span>
        </div>
        <div className={s.barras}>
          {TOP.map(([titulo, meta, a, b]) => (
            <BarraApilada
              key={titulo}
              titulo={titulo}
              meta={meta}
              valor={es(a + b)}
              tip={`${titulo}: ${a + b} veces, Extremoduro ${a}, Robe ${b}`}
              anchoE={(a / 237) * 100}
              anchoR={(b / 237) * 100}
            />
          ))}
        </div>
      </section>

      <section id="extremoduro-vs-robe" className={s.ancla}>
        <h3>Lo que Robe no recuperó</h3>
        <h2 className={s.col}>De veinticuatro canciones compartidas, veintidós suenan menos</h2>
        <p className={`${s.col} ${s.dim}`}>
          Veinticuatro canciones las tocaron las dos formaciones. La intuición dice que Robe
          rescató su pasado; los datos dicen lo contrario: solo <strong>dos</strong> suenan más con
          él que en las últimas giras de Extremoduro. Las otras <strong>veintidós</strong> suenan
          menos.
        </p>
        <p className={`${s.col} ${s.dim}`}>
          La comparación va entre épocas equivalentes, y esto importa: de las 459 fichas de
          concierto de Extremoduro, la mayoría de las antiguas{" "}
          <strong>no listan el repertorio</strong>, las de 1987 a 2002 suman 2,2 canciones por
          concierto y las de 2008 a 2014, 22,8. Así que se compara el Extremoduro de 2008-2014 (107
          conciertos con repertorio completo) con todo Robe (132, también completos). Dividir por
          las 459 hinchaba los porcentajes de Robe hasta tres veces.
        </p>

        <div className={s.leyenda}>
          <span>
            <i style={{ background: "var(--granate)" }} />
            Extremoduro 2008-2014 · 107 conciertos
          </span>
          <span>
            <i style={{ background: "var(--ocre)" }} />
            Robe 2017-2024 · 132 conciertos
          </span>
        </div>
        <div className={s.dumb}>
          {DUMB.map(([titulo, a, b, x]) => {
            const i = Math.min(a, b);
            const w = Math.abs(b - a);
            const crece = parseFloat(String(x).replace(",", ".")) >= 1;
            return (
              <div className={s.dumbFila} key={titulo}>
                <div className={s.dumbCab}>
                  <div className={s.filaTit}>{titulo}</div>
                  <div className={`${s.dumbX} ${s.num}${crece ? "" : ` ${s.dumbXBaja}`}`}>×{x}</div>
                </div>
                <div
                  className={s.dumbPista}
                  title={`${titulo}: ${coma(a)} % de los conciertos de Extremoduro → ${coma(b)} % de los de Robe`}
                >
                  <div className={s.dumbLinea} style={{ left: `${i}%`, width: `${w}%` }} />
                  <div className={`${s.dot} ${s.dotE}`} style={{ left: `${a}%` }} />
                  <div className={`${s.dot} ${s.dotR}`} style={{ left: `${b}%` }} />
                </div>
              </div>
            );
          })}
        </div>
        <div className={s.dumbEsc}>
          <span>0 %</span>
          <span>de los conciertos de su formación</span>
          <span>100 %</span>
        </div>

        <div className={`${s.nota} ${s.col}`}>
          El Extremoduro final tocaba un repertorio casi inmóvil:{" "}
          <strong>«Standby» en el 98,1 %</strong> de sus conciertos, «Puta» y «Salir» en el 97,2 %,
          «Dulce introducción al caos» y «Ama, ama, ama» en el 96,3 %. A Robe no hay nada que le
          pase del <strong>72 %</strong>. La rigidez estaba en la banda, no en el solista.
        </div>

        <div className={`${s.nota} ${s.col}`}>
          Las dos que sí crecen: <strong>«Contra todos»</strong>, de un 10,3 % a un 42,4 % (×4,1),
          y Extremoduro la estrenó en directo antes de que existiera en disco, y{" "}
          <strong>«Si te vas…»</strong>, de un 32,7 % a un 59,1 % (×1,8).
        </div>
      </section>

      <section id="lo-que-se-quedo-atras" className={s.ancla}>
        <h3>La otra cara</h3>
        <h2 className={s.col}>Lo que se quedó atrás</h2>
        <p className={`${s.col} ${s.dim}`}>
          Sesenta y tres composiciones que Extremoduro tocó en directo no volvieron a sonar en la
          etapa en solitario. Estas son las diez que más veces habían sonado.
        </p>
        <div className={s.barras}>
          {ATRAS.map(([titulo, meta, n, pct]) => (
            <BarraApilada
              key={titulo}
              titulo={titulo}
              meta={meta}
              valor={
                <>
                  {es(n)} <span>· {coma(pct)} %</span>
                </>
              }
              tip={`${titulo}: ${n} veces, el ${coma(pct)} % de los conciertos de Extremoduro`}
              anchoE={(n / 107) * 100}
            />
          ))}
        </div>
      </section>

      <section id="legado" className={s.ancla}>
        <h3>Dos repertorios</h3>
        <h2 className={s.col}>Robe dedicaba un tercio del concierto al legado</h2>
        <p className={`${s.col} ${s.dim}`}>
          Reparto de las interpretaciones por disco de origen. «Versiones» recoge lo que no es suyo:
          para Extremoduro son covers ajenos; para Robe, sobre todo el repertorio de Extremoduro.
        </p>

        <div className={s.dosColumnas}>
          <div>
            <h3 className={s.tituloE}>Extremoduro · 3.295 interpretaciones</h3>
            <BarrasDisco filas={DISCO_E} max={465} serie="e" />
          </div>
          <div>
            <h3 className={s.tituloR}>Robe · 2.286 interpretaciones</h3>
            <BarrasDisco filas={DISCO_R} max={667} serie="r" />
          </div>
        </div>

        <div className={`${s.nota} ${s.col}`}>
          El <strong>29,2 %</strong> de lo que tocaba Robe no salía de sus cuatro discos. En
          Extremoduro esa cifra era del <strong>5,2 %</strong>.
        </div>
      </section>

      <section>
        <h3>Treinta y ocho años</h3>
        <h2 className={s.col}>Los conciertos, año a año</h2>
        <p className={`${s.col} ${s.dim}`}>
          Conciertos documentados por año. Los años sin barra no tienen ninguno registrado: giras
          que no hubo, el parón de la pandemia y los dos años entre la disolución y el primer
          concierto en solitario.
        </p>

        <div className={s.leyenda}>
          <span>
            <i style={{ background: "var(--granate)" }} />
            Extremoduro
          </span>
          <span>
            <i style={{ background: "var(--ocre)" }} />
            Robe
          </span>
          <span>
            <i style={{ background: "rgba(237,228,211,.13)" }} />
            Sin conciertos registrados
          </span>
        </div>
        <div className={s.anios}>
          {Array.from({ length: 2024 - 1987 + 1 }, (_, k) => 1987 + k).map((y) => {
            const e = ANIOS_E[y] || 0;
            const r = ANIOS_R[y] || 0;
            const n = e || r;
            if (!n) {
              return (
                <div
                  key={y}
                  className={`${s.anio} ${s.anioCero}`}
                  title={`${y}: sin conciertos registrados`}
                >
                  <span />
                </div>
              );
            }
            return (
              <div
                key={y}
                className={s.anio}
                title={`${y}: ${n} conciertos de ${e ? "Extremoduro" : "Robe"}`}
              >
                <span
                  style={{
                    height: `${(n / 53) * 100}%`,
                    background: e ? "var(--granate)" : "var(--ocre)",
                  }}
                />
              </div>
            );
          })}
        </div>
        <div className={s.aniosEsc}>
          <span>1987</span>
          <span>1996 · el año de Agila, 53 conciertos</span>
          <span>2024</span>
        </div>
      </section>

      <section>
        <h3>La letra por dentro</h3>
        <h2 className={s.col}>Seis mil versos, uno de cada tres repetido</h2>
        <p className={`${s.col} ${s.dim}`}>
          Medido sobre las 132 composiciones canónicas, sin contar regrabaciones ni versiones en
          directo.
        </p>

        <div className={s.kpis} style={{ marginTop: 28 }}>
          <div className={s.kpi}>
            <b className={s.num}>6.078</b>
            <span>Versos en total</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>30,3 %</b>
            <span>Son una repetición</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>215</b>
            <span>Estribillos identificados</span>
          </div>
          <div className={s.kpi}>
            <b className={s.num}>
              70<span className={s.kpiDe}>/132</span>
            </b>
            <span>Composiciones con estribillo</span>
          </div>
        </div>

        <p className={`${s.col} ${s.dim}`} style={{ marginTop: 32 }}>
          Un estribillo no es solo un verso que se repite: es el que <em>vuelve</em>. De los 283
          versos que aparecen tres o más veces en su canción, 68 se caen porque sus apariciones se
          amontonan en un solo tramo, son letanías de entrada, no estribillos.
        </p>

        <div className={s.tablaWrap}>
          <table>
            <thead>
              <tr>
                <th>Los versos más repetidos</th>
                <th>Veces</th>
                <th>Canciones</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["¡Hijos de puta!", 16, 2],
                  ["De una patada rompo el Sol", 12, 1],
                  ["Luce la oscuridad;", 12, 1],
                  ["-Mama, ya he mamado", 11, 1],
                  ["A ver qué me dice después", 9, 1],
                  ["Tú en tu casa", 9, 1],
                  ["Y me tiemblan los pies a su lado", 9, 1],
                ] as [string, number, number][]
              ).map(([verso, veces, canciones]) => (
                <tr key={verso}>
                  <td>{verso}</td>
                  <td className="n">{veces}</td>
                  <td className="n">{canciones}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className={`${s.nota} ${s.col}`}>
          La canción con más versos es <strong>«Pedrá»</strong>, con 211: media hora en una sola
          pista. La que más deprisa se canta es «Te juzgarán sólo por tus errores (Yo no)», a 18,4
          versos por minuto; la más lenta, el cuarto movimiento de <em>Mayéutica</em>, a 5,9.
        </div>
      </section>

      <section>
        <h3>La deuda del setlist</h3>
        <h2 className={s.col}>Lo que se busca y no ha sonado</h2>
        <p className={`${s.col} ${s.dim}`}>
          Búsquedas mensuales en España (Ahrefs, octubre de 2026) frente a la presencia de esa
          canción en los escenarios.
        </p>

        <div className={s.tablaWrap}>
          <table>
            <thead>
              <tr>
                <th>Canción</th>
                <th>Búsquedas/mes</th>
                <th>Veces que ha sonado</th>
                <th>% de conciertos</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["Guerrero", "300", "58", "43,9 %"],
                  ["Desarraigo", "150", "17", "3,7 %"],
                  ["El camino de las utopías", "100", "91", "27,3 %"],
                  ["Su culo es miel", "60", "1", "0,2 %"],
                  ["Locura transitoria", "50", "51", "9,2 %"],
                  ["Entre interiores", "20", "26", "5,7 %"],
                  ["Mi voluntad", "20", "31", "6,8 %"],
                  ["Cerca del suelo", "10", "0", "sin registro"],
                ] as [string, string, string, string][]
              ).map(([cancion, vol, veces, pct]) => (
                <tr key={cancion}>
                  <td>{cancion}</td>
                  <td className="n">{vol}</td>
                  <td className="n">{veces}</td>
                  <td className="n">{pct}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className={`${s.nota} ${s.col}`}>
          <strong>«Su culo es miel»</strong> se busca sesenta veces al mes y ha sonado{" "}
          <strong>una sola vez</strong> en 459 conciertos. Y «Desarraigo», con ciento cincuenta
          búsquedas, apenas en el 3,7 % de ellos.
        </div>
      </section>

      <section className={s.fuentes}>
        <h3>Método y fuentes</h3>
        <p>
          Cada cifra de esta página sale de una fuente consultable y se puede regenerar con dos
          scripts del proyecto. El registro completo, con los hashes de cada página descargada y la
          verificación una a una de las once canciones, está en el documento de fuentes del
          estudio.
        </p>

        <h3>De dónde sale cada cosa</h3>
        <ul>
          <li>
            <strong>Repertorio y conciertos en directo:</strong>{" "}
            <a href="https://www.setlist.fm/stats/extremoduro-13d68da1.html">setlist.fm</a>,
            consultada el 6 y el 7 de octubre de 2026.
          </li>
          <li>
            <strong>Catálogo, letras, versos y estribillos:</strong> base de datos de Entre
            Interiores.
          </li>
          <li>
            <strong>Verificación de tracklists y fechas de disco:</strong>{" "}
            <a href="https://musicbrainz.org/">MusicBrainz</a>.
          </li>
          <li>
            <strong>Contraste de lo que nunca se tocó:</strong> el consultorio de Juancares,{" "}
            <a href="https://www.youtube.com/watch?v=fbAKGSeQGy4">capítulo 1x04</a> y{" "}
            <a href="https://www.youtube.com/watch?v=ReX6OLBnT90">capítulo 1x05</a>. Es trabajo de
            un tercero y se cita como tal: aquí sirve para corroborar una ausencia, no como dato
            propio.
          </li>
          <li>
            <strong>Volúmenes de búsqueda:</strong> Ahrefs, España, octubre de 2026.
          </li>
          <li>
            <strong>Mapa de provincias:</strong> datos públicos de contornos administrativos,
            simplificados para la web.
          </li>
        </ul>

        <h3>Lo que estas cifras no dicen</h3>
        <ul>
          <li>
            <strong>La mayoría de las fichas antiguas no listan el repertorio.</strong> De las 459
            de Extremoduro, las de 1987 a 2002 traen 2,2 canciones por concierto y las de 2008 a
            2014, 22,8: el <strong>78,5 % de las interpretaciones registradas sale de cuatro
            giras</strong> que son el 31 % de los conciertos. Por eso el ranking de lo más tocado
            favorece a lo que seguía en el repertorio al final, y por eso las comparaciones de esta
            página van entre épocas de densidad equivalente y no sobre el total.
          </li>
          <li>
            setlist.fm es un archivo colaborativo: 459 setlists no son todos los conciertos de
            Extremoduro, son los que alguien subió. La cobertura crece con los años, 1987 tiene uno
            registrado y 1996, cincuenta y tres, así que una canción de los primeros discos acumula
            menos toques por cómo está documentado el archivo, no necesariamente porque sonara
            menos. Por eso todas las comparaciones de esta página van normalizadas por número de
            conciertos.
          </li>
          <li>
            Las once se cuentan solo sobre discos de estudio y EP. Un corte que únicamente existe
            en un disco en directo no puede figurar como canción sin registro en directo.
          </li>
          <li>
            <strong>«No consta» no es «no ocurrió».</strong> Estas once no tienen registro
            conocido; si aparece uno, la lista se corrige y se dice. La afirmación que sostiene
            este estudio es sobre lo documentado, no sobre lo que pasó en cada noche de treinta y
            ocho años.
          </li>
          <li>
            Ciudades y recintos salen del índice de conciertos de setlist.fm, recorrido entero el 7
            de octubre de 2026: las 46 páginas de Extremoduro y las 14 de Robe. Los 591 conciertos
            cuadran con los totales que declara. <strong>23 no tienen ciudad</strong>: son entradas
            donde solo consta el festival.
          </li>
          <li>La fecha en que cada canción sonó por última vez no está en esta versión.</li>
          <li>
            <strong>Licencia.</strong> El listado de las once canciones sin registro se publica bajo{" "}
            <a href="https://creativecommons.org/licenses/by/4.0/deed.es" rel="license">
              CC BY 4.0
            </a>{" "}
            (<a href="/datos/once-canciones-sin-registro-en-directo.csv" download>
              descargar CSV
            </a>
            ): úsalo citando «Entre Interiores (entreinteriores.com)». Las cifras de directo
            proceden de setlist.fm, se rigen por sus condiciones y no se redistribuyen.
          </li>
        </ul>

        <p className={s.sello}>
          Entre Interiores · entreinteriores.com
          <br />
          Investigación y análisis: David Ruiz
          <br />
          Datos de directo: setlist.fm · Verificación de catálogo: MusicBrainz
          <br />
          Publicado el 7 de octubre de 2026
        </p>
      </section>
    </div>
  );
}
