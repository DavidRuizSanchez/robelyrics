# Fase 0: cierre de huecos (10-11-2026)

Plan aprobado el 10-11-2026 (revisado con Fable 5.1). Esta fase no lleva código ni toca prod: solo `SELECT`, DataForSEO y Wikipedia. La evidencia está en `SOURCES.md`, de A-21 a A-29.

## 1. Los murales (A-09 y A-10, resueltos)

- **Jesús Mateos Brea.** Su mural de Robe está **en Plasencia**. Lo dice nuestra referencia `_ref/robe-solo`: «le dedicó una avenida y un macromural de Jesús Mateos Brea que une su legado con la poesía de Manolo Chinato».
  - Forbes lo presenta como «artista placentino».
  - La **plaza Puerto de Béjar** solo la dice el narrador del vídeo, así que **no** va en ningún title.
  - Brea cuenta en primera persona (testimonio T-14) que Robe y Chinato le pidieron que el mural fuera su propia lectura de la obra.
  - Wikipedia no lo nombra. La grafía «Jesús Mateos Brea» la dan igual Forbes y nuestra referencia; Vozpopuli la abrevia a «J.M. Brea».
- **Primo.** El otro mural de Robe **existe**. Lo publica EFE en Vivir Ediciones (31-12-2025): obra del artista urbano lucense Primo, «en una de las fachadas de la céntrica plaza de San Martín», Robe con tres buitres, en tinta china sobre papel kraft.
- **Consecuencia.** «mural robe plasencia» (170 búsquedas de media, con 590 en agosto de 2026) busca *los* murales, no a Brea. La página que lo cubra tiene que ser **«Los murales de Robe en Plasencia»** (los dos) o una sección dentro de la pieza de Plasencia. No es la ficha de Brea. El title de Brea pasa a no nombrar el mural en exclusiva.

## 2. Demanda del tema Plasencia (A-21 y A-22)

DataForSEO (ES/es, 44 keywords, revalidado sin diferencias). Media de 12 meses y la serie de octubre de 2025 a septiembre de 2026:

| Keyword | Media | Lo que dice la serie |
|---|---|---|
| homenaje robe plasencia | 2.400 | **Pico**: 27.100 en dic-2025; 20-30 al mes desde junio |
| robe plasencia | 720 | Pico en dic-2025 (6.600) y mar-2026 (1.300); **base de 110-320 al mes** |
| robe iniesta plasencia | 260 | Pico en dic-2025; base de 30-140 |
| primeras flores amarillas | 260 | **Estacional**: 320/880/1.900 en mar/abr/may-2026 (el festival); casi 0 el resto |
| mural robe plasencia | 170 | **Sostenida y al alza**: 110-590 desde enero |
| dosis letal | 170 | Base de 90-170 [HIPÓTESIS: parte será la expresión genérica, no el grupo] |
| extremoduro plasencia | 110 | Base de 40-90 |
| historia de extremoduro | 90 | — |
| dosis letal robe | 70 | — |
| donde nacio robe | 50 | — |
| miembros de extremoduro | 1.900 | En caída: 1.000 → 70 al mes (la posiciona `/personas`) |

**En GSC el sitio casi no aparece en el tema** (del 14-08 al 06-11):
- «plasencia extremoduro»: 5 impresiones en `/extremoduro` (posición 12,4) y 4 en `/lugares/plasencia`.
- Las flores amarillas: 46 impresiones en el post del festival de 2027 y 31 en el concepto.
- Nada para «robe plasencia» ni para los murales.

**Ninguna página es dueña** de una demanda base de unas 300-500 búsquedas al mes (robe plasencia, robe iniesta plasencia, extremoduro plasencia, mural robe plasencia), más los picos.

## 3. Triaje de las 13 candidatas restantes y los 5 dudosos (A-23 a A-27)

Wikipedia ES (fuente oficial de grafía, criterio de David):

| Quién | Wikipedia | Decisión |
|---|---|---|
| Mariño (alcalde, 1987) | Sin artículo y sin mención. Lo nombra Ángel Lorenzo en primera persona (T-03) | **Sin ficha**: va en la pieza de Plasencia con el testimonio |
| Cándido Cabrera, José Antonio Hernández, Virgilio | Sin artículo ni mención | Sin ficha; lo que digan, solo como fondo |
| Fernando Pizarro | Sin artículo; el de Elia lo nombra («cedió la alcaldía de Plasencia a Fernando Pizarro, del PP», 2011) | Sin ficha: dato corroborado para la pieza de Plasencia |
| Enrique Tornero | Sin artículo; lo nombra Mondo Sonoro (concejal de Juventud) | Sin ficha: pieza de Plasencia |
| Marcos Peral, Miguel Ángel Corisco «Cori» | Sin artículo ni mención; los nombran Belén (T-07) y Susi (T-08) | Sin ficha: se nombran dentro de la ficha de quien los cita |
| Cholo, Pedro, Félix, Gustavo, Raúl | Solo nombre de pila o apellido dudoso. «Félix» en Wikipedia es **Félix Landa** (2002) y **Félix Arribas** (técnico): otras personas | Sin ficha |
| «Misma» y «Zosy» (E-038) | **Resuelto**: Luisma Beltrán y Zósimo «Zosi» Pascual (Wikipedia, «Extremoduro» y «Roberto Iniesta») | Miembros en la página de Dosis Letal |
| Ventura «Duerte» (E-023) | «Ventura» en Wikipedia es **Ventura Rico**, productor: otra persona | Sin identificar |
| Luis «Ba» (E-054), Jorge «Armestad» (E-067) | Nada | Sin identificar |
| Rafael «Rever» (E-059) | Wikipedia confirma la **final del Yamaha Band Explosion del 28-09-1989**, pero no nombra al jurado | El concurso va como dato; la persona, sin identificar |

**Resultado:** de las 24 candidatas, **4 tienen ficha propia** (Ángel Lorenzo, María Timón, Paco Doniga y Jesús Mateos Brea). Juano, Luisma Beltrán y Zosi Pascual van como miembros de Dosis Letal. Los políticos y la gente de los bares van a la pieza de Plasencia.

## 4. Lo que corrigió esta fase

- **Paco Doniga**: el testimonio dice «cuatro o cinco» temas, «algunos de Rory Gallagher». No dice «la mitad» (eso es del narrador) ni que la dedicatoria de Robe fuera un disco. Ya corregido en `propuesta_muestra.py`.
- **Susi Iglesias**: el «primer disco» es *Tú en tu casa, nosotros en la hoguera*. Nuestra referencia lo da como debut, con portada de Rafael Gallego, que es lo que ella cuenta. Deja de ser `[HIPÓTESIS]`.
- **Fuente 431**: no es prensa ajena, es nuestra referencia (`_ref/robe-solo`).

## 5. Fase 1 lista para revisar

`testimonios_borrador.md`: 14 testimonios de 6 personas, con las 14 citas comprobadas literalmente en su minuto (`scripts/validar_testimonios.py`).

## Cómo cambia el orden

1. Lo que más demanda tiene sin dueño es **Robe y Plasencia** (más los murales), no las personas. La fase 4 (la pieza de Plasencia) gana peso. Se mantiene detrás de la 2 y la 3 porque necesita los testimonios aprobados y que `/extremoduro` ya cuente los orígenes.
2. **Primeras flores amarillas** es estacional (marzo a mayo). Si se quiere captar 2027, la pieza tiene que estar publicada **antes de marzo de 2027**. Ya existe `/blog/flores-amarillas-2027-tributo-a-robe-en-plasencia`: se amplía esa, no se hace otra.
