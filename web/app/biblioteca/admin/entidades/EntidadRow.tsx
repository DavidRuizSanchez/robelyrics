"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ActionBar, Button, Card, Details, Notice, StatusBadge } from "@/components/admin/ui";

export type Propuesta = {
  id: number;
  tipo: string;
  nombre: string;
  qid: string | null;
  relaciones: { desde: string; predicado: string; detalle?: string }[];
  material: number | null;
  demanda: { volumen: number; fuente: string; fecha: string } | null;
  estado: string;
};

export type RelacionPendiente = {
  id: number;
  sujeto: string;
  sujeto_path: string | null;
  predicado: string;
  objeto: string;
  objeto_path: string | null;
  rol: string | null;
  fuentes: { kind: string; tier: string; url?: string; evidencia?: string }[];
};

const TIPO: Record<string, string> = {
  Person: "Persona",
  MusicGroup: "Grupo",
  Place: "Lugar",
  Organization: "Organización",
  EducationalOrganization: "Centro de estudios",
};

const PREDICADO: Record<string, string> = {
  memberOf: "miembro de",
  member: "tiene como miembro a",
  birthPlace: "nació en",
  deathPlace: "murió en",
  foundingLocation: "se fundó en",
  alumniOf: "estudió en",
  founder: "fundado por",
  location: "con sede en",
  event: "concierto",
  producer: "producido por",
};

async function enviar(url: string): Promise<void> {
  const res = await fetch(url, { method: "POST" });
  const data = (await res.json().catch(() => ({}))) as { error?: string };
  if (!res.ok) throw new Error(data.error || "No se pudo guardar.");
}

export function PropuestaRow({ item }: { item: Propuesta }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function decidir(accion: "aprobar" | "descartar" | "recuperar") {
    setBusy(accion);
    setErr(null);
    try {
      await enviar(`/biblioteca/admin/entidades/api/propuesta/${item.id}/${accion}`);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card tone={item.estado === "aprobada" ? "ok" : item.estado === "descartada" ? "neutral" : "warn"}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-serif text-[17px] text-ink">
            {item.qid ? (
              <a href={`https://www.wikidata.org/wiki/${item.qid}`} target="_blank" rel="noopener noreferrer" className="hover:underline">
                {item.nombre}
              </a>
            ) : (
              item.nombre
            )}
          </p>
          <p className="mt-0.5 text-sm text-ink-faint">
            {TIPO[item.tipo] ?? item.tipo}
            {item.qid && ` · ${item.qid}`}
            {` · ${item.material ?? 0} fuentes del corpus la nombran`}
            {item.demanda && ` · ${item.demanda.volumen} búsquedas/mes (${item.demanda.fecha})`}
          </p>
        </div>
        <StatusBadge tone={item.estado === "aprobada" ? "ok" : "neutral"}>{item.estado}</StatusBadge>
      </div>
      <Details summary={`De dónde sale (${item.relaciones.length})`} className="mt-2">
        <ul className="list-disc pl-5 text-sm text-ink-dim space-y-0.5">
          {item.relaciones.slice(0, 20).map((r, i) => (
            <li key={i}>
              {r.desde} {PREDICADO[r.predicado] ?? r.predicado}
              {r.detalle ? ` · ${r.detalle}` : ""}
            </li>
          ))}
        </ul>
      </Details>
      {err && (
        <div className="mt-3">
          <Notice onClose={() => setErr(null)}>{err}</Notice>
        </div>
      )}
      <ActionBar
        primary={
          item.estado === "propuesta" || item.estado === "descartada" ? (
            <Button variant="primary" onClick={() => decidir("aprobar")} loading={busy === "aprobar"} disabled={busy !== null}>
              Hacerle ficha
            </Button>
          ) : undefined
        }
        secondary={
          item.estado === "descartada" ? (
            <Button onClick={() => decidir("recuperar")} loading={busy === "recuperar"} disabled={busy !== null}>
              Recuperar
            </Button>
          ) : undefined
        }
        danger={
          item.estado !== "descartada" ? (
            <Button variant="danger" onClick={() => decidir("descartar")} loading={busy === "descartar"} disabled={busy !== null}>
              Descartar
            </Button>
          ) : undefined
        }
      />
    </Card>
  );
}

export function RelacionRow({ item }: { item: RelacionPendiente }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function decidir(accion: "aprobar" | "rechazar") {
    setBusy(accion);
    setErr(null);
    try {
      await enviar(`/biblioteca/admin/entidades/api/relacion/${item.id}/${accion}`);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card tone="warn">
      <p className="font-serif text-[17px] text-ink">
        {item.sujeto_path ? <a href={item.sujeto_path} className="hover:underline">{item.sujeto}</a> : item.sujeto}{" "}
        <span className="text-ink-faint">{PREDICADO[item.predicado] ?? item.predicado}</span>{" "}
        {item.objeto_path ? <a href={item.objeto_path} className="hover:underline">{item.objeto}</a> : item.objeto}
        {item.rol && <span className="text-ink-dim"> · {item.rol}</span>}
      </p>
      <Details summary={`Fuentes (${item.fuentes.length})`} className="mt-2">
        <ul className="list-disc pl-5 text-sm text-ink-dim space-y-0.5">
          {item.fuentes.map((f, i) => (
            <li key={i}>
              {f.tier} · {f.kind}
              {f.url && (
                <>
                  {" · "}
                  <a href={f.url} target="_blank" rel="noopener noreferrer" className="underline">
                    {f.url.replace(/^https?:\/\//, "").slice(0, 70)}
                  </a>
                </>
              )}
              {f.evidencia && <span className="block text-ink-faint">{f.evidencia}</span>}
            </li>
          ))}
        </ul>
      </Details>
      {err && (
        <div className="mt-3">
          <Notice onClose={() => setErr(null)}>{err}</Notice>
        </div>
      )}
      <ActionBar
        primary={
          <Button variant="primary" onClick={() => decidir("aprobar")} loading={busy === "aprobar"} disabled={busy !== null}>
            Es verdad: publicarla
          </Button>
        }
        danger={
          <Button variant="danger" onClick={() => decidir("rechazar")} loading={busy === "rechazar"} disabled={busy !== null}>
            Rechazar
          </Button>
        }
      />
    </Card>
  );
}
