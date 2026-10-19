"use client";

import Term from "@/components/admin/Term";
import {
  Data,
  Details,
  StatusBadge,
  Table,
  cx,
  inputClass,
  tdClass,
} from "@/components/admin/ui";
import {
  CONFIDENCE_LABEL,
  PLACEMENT_DECISION,
  PLACEMENT_VIA,
  bandaParecido,
  etiqueta,
  type Etiqueta,
} from "@/lib/admin/labels";
import type { PlacementCandidate, PlacementGroup } from "./page";

function fmtNum(n: number, dec = 0): string {
  return n.toLocaleString("es-ES", { maximumFractionDigits: dec });
}

/** La decisión tal y como hay que leerla. Ampliar una página de CÓDIGO no se
 *  puede hacer con el motor: es una mejora manual y se avisa como tal. */
function decisionDe(g: PlacementGroup): Etiqueta {
  const destino = g.candidates[0];
  if (g.decision === "ampliar" && destino && !destino.mergeable) {
    return {
      label: "Mejora manual",
      tone: "warn",
      hint: "La página vive en el código: el motor no puede ampliarla.",
    };
  }
  return etiqueta(PLACEMENT_DECISION, g.decision);
}

/**
 * Un grupo del reparto: qué búsquedas son, qué propone el sistema y por qué, y
 * qué quieres hacer con ellas. La evidencia completa va plegada.
 */
export default function PlacementGroupCard({
  g,
  volumes,
  value,
  onChange,
  disabled,
}: {
  g: PlacementGroup;
  volumes: Record<string, number>;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  const dec = decisionDe(g);
  const volTotal = g.keywords.reduce((acc, k) => acc + (volumes[k] ?? 0), 0);
  const conocido = g.keywords.some((k) => k in volumes);
  const conf = g.decision === "cubierto" ? null : etiqueta(CONFIDENCE_LABEL, g.confidence);
  const motivosVia = (g.via ?? []).map((v) => PLACEMENT_VIA[v]).filter(Boolean);
  const selectId = `destino-${g.keywords.join("-")}`;

  return (
    <div className="rounded-md border border-divider bg-bg/60 p-3 md:p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap gap-x-2 gap-y-1">
            {g.keywords.map((k) => (
              <Data key={k}>«{k}»</Data>
            ))}
          </p>
          <p className="mt-0.5 text-xs text-ink-faint">
            {conocido ? `${fmtNum(volTotal)} búsquedas/mes` : "volumen —"}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge tone={dec.tone} title={dec.hint}>
            {dec.label}
          </StatusBadge>
          {conf && <StatusBadge tone={conf.tone}>{conf.label}</StatusBadge>}
        </div>
      </div>

      {g.headline && <p className="mt-3 text-ink leading-snug">{g.headline}</p>}
      {motivosVia.length > 0 && (
        <p className="mt-1 text-sm text-ink-dim">Por qué: {motivosVia.join("; ")}.</p>
      )}

      <div className="mt-3 flex flex-col sm:flex-row sm:items-center gap-2 min-w-0">
        <label htmlFor={selectId} className="text-sm text-ink-dim shrink-0">
          Qué hacer con estas búsquedas:
        </label>
        <select
          id={selectId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={cx(inputClass, "min-w-0 sm:flex-1 truncate")}
        >
          {g.options.map((o) => (
            <option key={o.value} value={o.value} className="bg-bg">
              {o.label}
              {o.recommended ? " (recomendado)" : ""}
            </option>
          ))}
        </select>
      </div>

      {(g.candidates.length > 0 || g.reasons.length > 0) && (
        <Details summary="Ver en qué se basa" className="mt-3">
          {g.reasons.length > 0 && (
            <ul className="mb-3 list-disc pl-5 space-y-1 text-sm text-ink-dim">
              {g.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
          {g.candidates.length > 0 && <EvidenceTable candidates={g.candidates} />}
        </Details>
      )}
    </div>
  );
}

function EvidenceTable({ candidates }: { candidates: PlacementCandidate[] }) {
  return (
    <Table
      head={[
        "Página tuya",
        <Term key="i" k="impresiones">
          Veces en Google
        </Term>,
        <Term key="p" k="posicion">
          Posición media
        </Term>,
        <Term key="s" k="parecido">
          Parecido
        </Term>,
        "Nota",
      ]}
    >
      {candidates.map((c) => {
        const notas = [
          c.kind === "code" && "vive en el código (mejora manual)",
          c.is_anchor && "ficha de la entidad principal",
          c.serp_rank !== null && `sale ${c.serp_rank}.ª en Google ahora mismo`,
        ].filter(Boolean);
        return (
          <tr key={c.path}>
            <td className={tdClass}>
              <a
                href={c.path}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-[13px] text-ink hover:text-accent break-all"
              >
                {c.path} ↗
              </a>
            </td>
            <td className={cx(tdClass, "font-mono")}>
              {c.gsc_impressions > 0 ? fmtNum(c.gsc_impressions) : "—"}
            </td>
            <td className={cx(tdClass, "font-mono")}>
              {c.gsc_position === null ? "—" : fmtNum(c.gsc_position, 1)}
            </td>
            <td className={tdClass}>
              {c.similarity === null ? (
                "—"
              ) : (
                <>
                  {bandaParecido(c.similarity)}{" "}
                  <span className="font-mono text-ink-faint">({fmtNum(c.similarity, 2)})</span>
                </>
              )}
            </td>
            <td className={cx(tdClass, "text-ink-dim")}>{notas.join(" · ") || "—"}</td>
          </tr>
        );
      })}
    </Table>
  );
}
