# Personas del cap. 64: criba y propuesta (muestra de 10)

Plan del 10-11-2026, pasos 2 a 4b. **No se ha creado nada.** Esto es la muestra de 10 para validar el criterio antes de hacer las otras 14 candidatas y las 12 fichas que ya existen.

Para que una persona entre, hacen falta dos cosas (tus criterios):

- **Hechos corroborados**: un hecho se afirma solo con una fuente web descargada, otra fuente del corpus de **otro autor**, nuestra BD o el testimonio de primera mano de la persona en el vídeo.
- **Lugar en la historia**: tiene que ser de la escena o una figura pública con papel propio.

Lo que solo cuenta el narrador, o los otros vídeos de Juancares, es **fondo**: orienta, pero no se escribe.

Ficheros:
- `personas_propuesta_muestra.csv`: una fila por persona, con title y description ya validados.
- `relaciones_muestra.csv`: matriz de datos estructurados.
- `criba_personas.csv`: las 77 personas.
- `SOURCES.md`: fuentes y registro A-nn.

## 1. Criba de las 77 personas (A-01)

| Decisión | Personas | Qué pasa con ellas |
|---|---|---|
| Candidata | 24 (16 de la escena, 8 figuras públicas) | Se analizan una a una |
| Ya tiene ficha | 12 | Paso 4: qué aporta el vídeo a su ficha |
| A la ficha de Robe | 13 | Familia y gente privada (padres, hermanos, la matrona, el profesor de La Salle…): sin ficha propia |
| Contexto | 23 | Papel tangencial (los futbolistas de la peña, los presidentes de la Junta, Franco, Aznar…). El narrador queda fuera por la regla de la voz |
| Identificar antes | 5 | El nombre sale dudoso de Whisper |

**Al menos uno de los 5 ya se resuelve (A-04).** Los «Misma» y «Zosy» de Whisper (E-038) son **Luisma Beltrán** y **Zósimo «Zosi» Pascual**, de Dosis Letal, según Wikipedia.

## 2. Lo que dice la muestra

| Persona | Hechos afirmables | Demanda (DataForSEO, ES) | Recomendación |
|---|---|---|---|
| Elia Blanco (E-020) | 6 | «elia maria blanco» 40 · «elia blanco» 20 | **Crear, si decides el punto delicado** (abajo) |
| José Luis Díaz Sánchez (E-028) | 3 | n/d en las 3 variantes | **Crear** |
| Paco Doniga (E-039) | 3 | «paco doniga» 10 | **Crear** |
| Ángel Lorenzo (E-040) | 4 | n/d | **Crear** y darlo de alta en la formación de Extremoduro |
| María Timón (E-050) | 4 | «maria timon» 10 | **Crear** y sus créditos de coros |
| Jesús Mateos Brea (E-068) | 2 | «jesus mateos brea» 40 · «mural robe plasencia» 170 | **Crear**, y valorar una página del mural |
| Belén (E-049) | 2 | «belen extremoduro» 10 | Créditos sí; ficha cuando se sepa el apellido |
| Juano (E-037) | 1 | «dosis letal» 170 · «dosis letal robe» 70 | Sin ficha propia: sección en la futura página de **Dosis Letal** |
| Susi Iglesias (E-055) | 1 | n/d | Sin ficha: sección «la portada» en la ficha del primer disco y crédito de arte |
| Paramio (E-047) | 1 | «paramio extremoduro» 10 | Identificar antes |
| Javi Génesis (E-048) | 0 | n/d | Sin ficha: sus bares van a la fase de lugares |

`n/d` = DataForSEO no devuelve volumen. No es «0 búsquedas».

### Tres hallazgos que cambian el plan

1. **La demanda no está en los nombres, está en los temas.** Ninguna persona de la muestra pasa de 40 búsquedas al mes, y en GSC ninguna recibe impresiones por su nombre (A-14). En cambio:
   - «dosis letal» tiene 170 y «dosis letal robe», 70.
   - «mural robe plasencia» tiene 170.
   - Las portadas de los discos ya reciben impresiones en GSC: «portadas discos extremoduro», 117.

   Las fichas de persona valen por el grafo y por completar la historia, no por tráfico propio. Por eso propongo adelantar **Dosis Letal** (grupo) y **el mural** (obra) en el orden de fases.
2. **El vídeo trae datos que la BD no tiene.** El primer batería de Extremoduro fue **Ángel Lorenzo** (1987, unos cuatro meses), y en la BD la formación empieza en William (A-05, A-15). Las coristas de cuatro discos son **María Timón** y Belén, acreditadas canción a canción en Wikipedia (A-06).
3. **Hay que distinguir «otra fuente» de «otro vídeo del mismo autor».** De las 48 menciones de la muestra en el corpus de prod, 40 son de Juancares. De las otras 8:
   - Mondo Sonoro (3), Trembol (2) y la prensa (1) corroboran de verdad.
   - Jot Down es un falso positivo.
   - La entrevista de Disco Cross de 1993 (subida por Pako Beer) nombra a Belén en los coros de «Pepe Botika». No está claro quién habla, así que va de apoyo, no como cita (A-17).

### Decisiones que te tocan

- **Elia Blanco (A-07).** Su artículo de Wikipedia dice que fue condenada por fraude y prevaricación y que ingresó en prisión en 2015. Es una figura pública viva. O la ficha lo recoge con su fuente, o no se hace: callarlo en una biografía sería sesgarla. Lo que nos interesa de ella (concejala de 1987 a 1991, alcaldesa de 2003 a 2011, amistad con Robe) está corroborado.
- **Paramio (A-11).** Mondo Sonoro lo llama «uno de los cofundadores de Extremoduro», y no lo dice ni la BD ni Wikipedia. Hay que aclararlo antes de afirmar nada, también en la formación.
- **El mural (A-10).** En una búsqueda web salió **otro** mural de Robe en Plasencia, de un artista llamado Primo. No lo he podido comprobar en su fuente: `[HIPÓTESIS]`. Si se hace la página del mural, hay que desambiguar.

## 3. Propuesta on-page (validada con `seo_style`)

Todos los titles y descriptions pasan `title_verdict` y `desc_verdict`. Se validaron contra el **esqueleto** de H2 y hechos, porque la ficha no existe todavía. Cuando el motor escriba el cuerpo se vuelven a pasar.

| Persona | Title (caracteres) | Description (caracteres) | H2 |
|---|---|---|---|
| Elia Blanco | Elia Blanco: alcaldesa de Plasencia y amiga de Robe (51) | Conoce a Elia Blanco, concejala y alcaldesa de Plasencia, y su papel en la relación entre la ciudad, Robe y Extremoduro. (120) | Quién es · Concejala (1987-1991) · Su relación con Robe · Alcaldesa (2003-2011) y la vuelta de Extremoduro |
| José Luis Díaz Sánchez | José Luis Díaz Sánchez: el alcalde que vetó a Extremoduro (57) ⚠ no cubre «jose luis diaz plasencia» (aviso, no bloquea) | Descubre quién fue José Luis Díaz Sánchez, el alcalde de Plasencia que vetó a Extremoduro, y la carta con la que Robe le respondió. (131) | Quién es · El veto · La carta de Robe · El fin de su etapa (2003) |
| Paco Doniga | Paco Doniga: el bajista de Dosis Letal, primer grupo de Robe (60) | Conoce a Paco Doniga, bajista de Dosis Letal, el primer grupo de Robe, y su papel en los comienzos de Extremoduro en Plasencia. (127) | Quién es · Bajista de Dosis Letal · El concierto del campo de fútbol · La dedicatoria de Robe |
| Ángel Lorenzo | Ángel Lorenzo: el primer batería de Extremoduro (47) | Descubre cómo Ángel Lorenzo tocó la batería en los primeros ensayos de Extremoduro, con Robe y Kaíto, en la Plasencia de 1987. (126) | Quién es · El primer batería (1987) · Del Jazz a la Casa de la Salud · Por qué le sustituyó William |
| María Timón | María Timón: la corista de Somos unos animales y Deltoya (56) | Conoce a María Timón, la corista que puso voz en Somos unos animales y Deltoya junto a Belén, y en qué canciones de Extremoduro canta. (134) | Quién es · Coros en Somos unos animales · Voces en Deltoya · Del Bar Tertulia a Extremoduro |
| Jesús Mateos Brea | Jesús Mateos Brea: el mural de Robe y Chinato en Plasencia (58) | Descubre el mural de Jesús Mateos Brea en Plasencia, el homenaje que une la palabra de Robe con la poesía de Manolo Chinato. (124) | Quién es · El mural de Robe y Manolo Chinato · Otros murales en Plasencia |

Las guardas cazaron tres fallos en la primera versión, ya corregidos:
- La description de Ángel Lorenzo repetía el title.
- El title de María Timón tenía 68 caracteres, por encima del máximo de 65.
- El title de Elia («la alcaldesa que trajo a Extremoduro») se apoyaba en un dato que solo cuenta el narrador.

Cada hecho con su fuente está en `muestra_evidencia.json`. Dos que conviene tener presentes:
- **Ángel Lorenzo**: lo de por qué le sustituyó William solo lo cuenta el vídeo. Hay que comprobarlo en su testimonio antes de escribir esa sección.
- **Susi Iglesias**: que el «primer disco» del que habla sea *Tú en tu casa, nosotros en la hoguera* (1990, el primero por año en la BD) es una `[HIPÓTESIS]`. Ella dice «primer disco».

## 4. Relaciones en datos estructurados (paso 4b)

`relaciones_muestra.csv` tiene 26 relaciones para las 10 personas. Cada una lleva su propiedad de schema.org, la inversa, el `@id` del destino, la evidencia y si el dato existe hoy en la BD.

| Relación | Propiedad | ¿Dónde se guarda hoy? |
|---|---|---|
| Ángel Lorenzo → Extremoduro (batería, 1987) | `memberOf` + `OrganizationRole` | `band_memberships`: **existe**, solo hay que dar el alta |
| María Timón → 7 canciones (coros/voces) | `contributor` en `MusicRecording` | `song_credits`: **existe**, pero hoy solo tiene 13 filas con roles de autoría (`adaptacion`, `poema_original`, `musica`, `colaboracion`). Haría falta un rol nuevo, `coros`, y que el JSON-LD lo pinte como `contributor` |
| Belén → 3 discos (coros) | `contributor` | `song_credits` con `credited_name` y `person_id` vacío (el modelo lo admite) |
| Paco Doniga, Juano → Dosis Letal | `memberOf` | **No existe**: hace falta el grupo |
| Elia, José Luis Díaz → Ayuntamiento de Plasencia, partido | `worksFor` / `jobTitle` / `memberOf` | **No existe** |
| Elia → Robe, Ángel → Luis «von Fanta» | `knows` | **No existe** |
| Mateos Brea → el mural; el mural → Robe, Chinato | `creator`, `about` / `subjectOf` | **No existe**: obra nueva |
| Susi Iglesias → primer disco (arte) | `creator` | **No existe**: crédito de arte |
| Elia → Cabezuela del Valle; Mateos Brea → Plasencia | `birthPlace` / `homeLocation` → `/lugares/…#place` | **No existe**. Además, hoy `birthPlace` es texto suelto |

Conclusión: de las 26 filas de la matriz, solo caben en las tablas de hoy la membresía de Ángel Lorenzo y los créditos de coros de María Timón y Belén (estos, con el rol nuevo `coros`). Para el resto hace falta el modelo del paso 5: una tabla de relaciones tipadas con su fuente, de la que salgan a la vez las aristas de `build_graph` y el JSON-LD. Sin evidencia no hay propiedad.

## 5. Antes de crear: lo que hay que cerrar

Esfuerzo sin medir: todo esto es `[HIPÓTESIS]` hasta abrir el código.

1. **Páginas pobres.**
   - Hoy cualquier fila de `persons` sale como página indexable y entra en el hub (A-03). Las 48 personas de prod tienen ficha publicada (A-02), así que una guarda «noindex y fuera del hub sin ficha publicada» **no toca ninguna página que exista**.
   - Va ligada a cómo publicar, que decides tú.
2. **Tabla de relaciones tipadas.** Con su fuente; alimenta `build_graph` y el JSON-LD de `personas/[slug]/page.tsx` (y de paso se junta el `personNode()` duplicado de `schema-graph.ts`).
3. **El motor y su material.**
   - Poder fijar una fuente en el dossier (la 1756).
   - Que `corroborar` corra en `generate_deep` y `augment_deep`, porque hoy solo lo usa `merge_deep`.
   - Que el testimonio de primera mano cuente como afirmable.
4. **Aristas `mentions`.** `generate_deep` guarda `entities=[]`, así que una ficha nueva no las genera.
5. **Foto.** La de `seed_persons` no pasa por `image_guard`.

## Siguiente paso

Si te vale el criterio de la muestra, hago lo mismo con las otras 14 candidatas y con las 12 fichas existentes (paso 4), y cierro el informe completo con su validación.
