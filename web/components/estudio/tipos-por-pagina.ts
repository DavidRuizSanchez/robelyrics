// Forma de `datos-por-pagina.ts`, que genera `api/scripts/pr/build_page_data.py`.

export type DatoArtista = {
  setlists: number;
  toques: number;
  /** % de las interpretaciones registradas que no son de sus discos (versiones y otros). */
  pct_ajeno: number;
  ciudades: number;
  provincias: number;
  fuera_de_espana: number;
  desde: string;
  hasta: string;
};

export type DatoDisco = {
  toques: number;
  pct: number;
  setlists: number;
  /** Cuántas de las once sin registro en directo son de este disco. */
  once: number;
};

export type DatoCancion = {
  /** Interpretaciones registradas con Extremoduro y con Robe. */
  e: number;
  r: number;
  artista: string;
  once: boolean;
  /** Ficha canónica de la composición (la del disco más antiguo). */
  canonica: string;
};

type BaseLugar = {
  nombre: string;
  n: number;
  extremoduro: number;
  robe: number;
  primero: string | null;
  primero_recinto: string | null;
  ultimo: string | null;
  /** Si aquí fue el primer concierto documentado de todos (19-09-1987). */
  es_el_primero: boolean;
};

export type DatoLugar =
  | (BaseLugar & {
      tipo: "ciudad";
      provincia: string | null;
      provincia_n: number;
      /** Puesto de la provincia en España; null si empata con otra. */
      provincia_rank: number | null;
    })
  | (BaseLugar & { tipo: "region"; provincias: Record<string, number>; ciudades: number })
  | (BaseLugar & { tipo: "pais"; ciudades: string[] });

export type DatosPorPagina = {
  artistas: Record<string, DatoArtista>;
  discos: Record<string, DatoDisco>;
  canciones: Record<string, DatoCancion>;
  lugares: Record<string, DatoLugar>;
};
