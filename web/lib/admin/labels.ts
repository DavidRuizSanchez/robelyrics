// Vocabulario ÚNICO del panel admin: códigos del backend → frase en castellano
// llano + tono. Si una pantalla necesita nombrar un estado, sale de aquí; así
// todo el panel dice lo mismo con las mismas palabras.
//
// TS puro (sin React): sirve igual en server y client components.

export type Tone = "ok" | "warn" | "danger" | "info" | "neutral" | "accent";

export type Etiqueta = { label: string; tone: Tone; hint?: string };

/** Busca un código en un mapa; si el backend trae uno nuevo, se enseña tal cual. */
export function etiqueta<K extends string>(
  mapa: Record<K, Etiqueta>,
  codigo: string | null | undefined,
): Etiqueta {
  if (!codigo) return { label: "—", tone: "neutral" };
  return (mapa as Record<string, Etiqueta>)[codigo] ?? { label: codigo, tone: "neutral" };
}

// ── Blog ────────────────────────────────────────────────────────────────────

/** Tipos de pieza (propuestas y posts comparten el mismo campo `kind`). */
export const KIND_LABEL: Record<string, string> = {
  editorial: "Editorial",
  news: "Noticia",
  anniversary: "Efeméride de Robe",
  "album-anniversary": "Aniversario de disco",
  spotlight: "Análisis de canción",
  evergreen: "Tema de fondo",
};

export function kindLabel(kind: string | null | undefined): string {
  if (!kind) return "—";
  return KIND_LABEL[kind] ?? kind;
}

export type ProposalStatus = "proposed" | "approved" | "scheduled" | "used" | "discarded";

export const PROPOSAL_STATUS: Record<ProposalStatus, Etiqueta> = {
  proposed: { label: "Por decidir", tone: "warn", hint: "Nadie la ha aprobado todavía." },
  approved: { label: "Aprobada", tone: "info", hint: "Se está escribiendo o espera fecha." },
  scheduled: { label: "Programada", tone: "ok", hint: "Tiene fecha de publicación." },
  used: { label: "Ya escrita", tone: "ok", hint: "Se convirtió en un post." },
  discarded: { label: "Descartada", tone: "neutral" },
};

export type PostStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "scheduled"
  | "published"
  | "rejected";

export const POST_STATUS: Record<PostStatus, Etiqueta> = {
  draft: { label: "Borrador", tone: "neutral" },
  pending_review: { label: "Por revisar", tone: "warn", hint: "Espera tu visto bueno." },
  approved: { label: "Aprobado", tone: "info" },
  scheduled: { label: "Programado", tone: "info" },
  published: { label: "Publicado", tone: "ok" },
  rejected: { label: "Rechazado", tone: "neutral" },
};

/** Qué control de calidad retuvo un post (`review_blocked_by`). */
export const GATE_LABEL: Record<string, string> = {
  lyrics: "el control de citas de letra",
  rigor: "el editor jefe (rigor)",
  completeness: "el control de completitud",
  facts: "el control de datos de catálogo",
  fuentes: "el control de fuentes externas",
};

// ── Reparto de keywords (content_placement) ─────────────────────────────────

export type PlacementDecision = "ampliar" | "nuevo" | "cubierto";

export const PLACEMENT_DECISION: Record<PlacementDecision, Etiqueta> = {
  ampliar: {
    label: "Ampliar una página",
    tone: "info",
    hint: "Ya tienes una página que encaja: mejor sumarle esto que escribir otra.",
  },
  nuevo: {
    label: "Contenido nuevo",
    tone: "neutral",
    hint: "Ninguna página tuya responde a esto todavía.",
  },
  cubierto: {
    label: "Ya cubierta",
    tone: "ok",
    hint: "Una página tuya ya lo responde y sale en Google: escribir más no ayuda.",
  },
};

export const CONFIDENCE_LABEL: Record<"alta" | "media" | "baja", Etiqueta> = {
  alta: { label: "seguridad alta", tone: "ok" },
  media: { label: "seguridad media", tone: "warn" },
  baja: { label: "seguridad baja", tone: "neutral" },
};

/** Cómo se decidió el destino de un grupo (`via` en la API). */
export const PLACEMENT_VIA: Record<string, string> = {
  gsc: "Google ya enseña esa página para estas búsquedas",
  titulo: "La búsqueda nombra una canción o un disco que tiene ficha",
  semantica: "El contenido de la página se parece mucho a lo que se busca",
};

/** Umbral real de `content_placement.SIM_AMPLIAR`: a partir de aquí se propone ampliar. */
export const SIM_ALTA = 0.6;

export function bandaParecido(sim: number | null): string {
  if (sim === null) return "—";
  if (sim >= SIM_ALTA) return "parecido alto";
  if (sim >= 0.45) return "parecido medio";
  return "parecido bajo";
}

/** Texto de cada opción del selector de destino. */
export function opcionDestino(value: string, label: string): string {
  if (value === "skip") return "Quitar estas búsquedas de la idea";
  if (value === "new") return "Escribirlas en un post nuevo";
  return `Ampliar ${label}`;
}

// ── Instagram ───────────────────────────────────────────────────────────────

export type IgStatus = "proposed" | "pending" | "prepared" | "published" | "failed" | "discarded";

export const IG_STATUS: Record<IgStatus, Etiqueta> = {
  proposed: { label: "Propuesta", tone: "warn", hint: "Espera que la apruebes." },
  pending: { label: "En cola", tone: "info", hint: "Aprobada; falta preparar imagen y texto." },
  prepared: { label: "Lista", tone: "ok", hint: "Imagen y texto preparados: sale en su turno." },
  published: { label: "Publicada", tone: "ok" },
  failed: { label: "Falló", tone: "danger", hint: "Instagram la rechazó o no se pudo preparar." },
  discarded: { label: "Descartada", tone: "neutral" },
};

export const IG_CONTENT_TYPE: Record<string, string> = {
  quote: "Frase de canción",
  ephemeris: "Efeméride",
  anecdote: "Anécdota",
  robe_quote: "Cita de Robe",
  news: "Noticia",
  blog: "Blog",
};

export type ClipStatus = "requested" | "downloading" | "ready" | "published" | "retired" | "failed";

export const CLIP_STATUS: Record<ClipStatus, Etiqueta> = {
  requested: {
    label: "Pedido",
    tone: "info",
    hint: "Lo baja el ordenador de casa; suele tardar unos minutos.",
  },
  downloading: { label: "Descargando", tone: "info", hint: "Montándose en el ordenador de casa." },
  ready: { label: "Listo", tone: "ok", hint: "Montado y subido: se puede usar en un post." },
  published: { label: "Publicado", tone: "ok" },
  retired: { label: "Retirado", tone: "neutral" },
  failed: { label: "Falló", tone: "danger" },
};

// ── SEO ─────────────────────────────────────────────────────────────────────

export type OpportunityStatus =
  | "detected"
  | "approved"
  | "drafted"
  | "applied"
  | "discarded"
  | "noop"
  | "failed";

export const OPPORTUNITY_STATUS: Record<OpportunityStatus, Etiqueta> = {
  detected: { label: "Detectada", tone: "warn", hint: "Decide si merece la pena preparar algo." },
  approved: { label: "Preparando borrador", tone: "info", hint: "Tarda unos minutos." },
  drafted: { label: "Borrador listo", tone: "warn", hint: "Revisa el antes/después y publica." },
  applied: { label: "Publicada", tone: "ok" },
  discarded: { label: "Descartada", tone: "neutral" },
  noop: {
    label: "Sin mejora posible",
    tone: "neutral",
    hint: "No hay material verificado que mejore la página: no se toca.",
  },
  failed: { label: "Falló", tone: "danger" },
};

export const OPPORTUNITY_ACTION: Record<string, Etiqueta> = {
  meta: {
    label: "Mejorar title y description",
    tone: "info",
    hint: "La página ya responde, pero lo que se ve en Google no lo promete.",
  },
  body: {
    label: "Ampliar el contenido",
    tone: "info",
    hint: "La página no responde a lo que se busca: se añade sin tocar lo que ya dice.",
  },
  merge: {
    label: "Fusionar una propuesta del blog",
    tone: "accent",
    hint: "Lo de una idea del blog se suma a esta página en vez de escribir otra.",
  },
};

export const SEO_CONTENT_STATUS: Record<string, Etiqueta> = {
  draft: { label: "Borrador", tone: "warn" },
  published: { label: "Publicada", tone: "ok" },
};

// ── Erratas ─────────────────────────────────────────────────────────────────

export type ErrataStatus = "pending" | "auto_resolved" | "needs_human" | "applied" | "rejected";

export const ERRATA_STATUS: Record<ErrataStatus, Etiqueta> = {
  pending: { label: "Sin revisar", tone: "warn" },
  auto_resolved: { label: "Resuelta sola", tone: "ok" },
  needs_human: { label: "Necesita que decidas", tone: "warn" },
  applied: { label: "Corregida", tone: "ok" },
  rejected: { label: "Rechazada", tone: "neutral" },
};

export const ERRATA_TARGET: Record<string, string> = {
  song_lyrics: "Letra",
  authorship: "Autoría",
  catalog: "Disco / año",
  interpretation: "Interpretación",
  image: "Imagen",
};

/** Quién avisó, cuando el aviso lo abre un proceso automático y no una persona. */
export const ERRATA_REPORTER: Record<string, string> = {
  authorship_consensus: "el motor de consenso (autorías)",
  audit_images: "la auditoría de imágenes",
};

/** Qué tipo de dato corrigió solo el consenso (`claim_kind`). */
export const CLAIM_KIND: Record<string, string> = {
  song_authorship: "Autoría de canción",
  album_year: "Año de un disco",
  lyric_line: "Verso de una letra",
  album_created: "Disco dado de alta",
};

// ── Suscriptores ────────────────────────────────────────────────────────────

export const SUBSCRIBER_STATUS: Record<string, Etiqueta> = {
  pending: { label: "Sin confirmar", tone: "warn" },
  confirmed: { label: "Confirmado", tone: "ok" },
  unsubscribed: { label: "Dado de baja", tone: "neutral" },
  bounced: { label: "Rebota", tone: "danger" },
};

// ── Glosario (lo usa <Term>) ────────────────────────────────────────────────

export const GLOSARIO = {
  impresiones:
    "Veces que Google enseñó la página en sus resultados (Search Console). No son visitas.",
  posicion:
    "Puesto medio en Google para esas búsquedas. 1 es el primero; del 11 en adelante, segunda página.",
  volumen: "Búsquedas al mes en España, según DataForSEO.",
  parecido:
    "Cuánto se parece el contenido de la página a lo que se busca (similitud de 0 a 1). A partir de 0,60 se considera alto.",
  canibalizacion:
    "Dos páginas tuyas compitiendo por la misma búsqueda: Google duda y suelen salir peor las dos.",
  ampliar: "Sumar una sección a una página que ya existe en vez de escribir otra.",
  cubierta:
    "La página ya responde a la búsqueda y lo promete en Google: lo que falta es subir puestos, no texto.",
  mejoraManual:
    "La página vive en el código, no en la base de datos: el motor no puede ampliarla y hay que hacerlo a mano.",
  siOSi:
    "Publica aunque no pase los controles de calidad y longitud. Úsalo solo si sabes por qué.",
  needsHuman:
    "Una guarda no pudo confirmar algo (identidad, foto o afirmación): necesita que lo mires tú.",
} as const;

export type TerminoGlosario = keyof typeof GLOSARIO;
