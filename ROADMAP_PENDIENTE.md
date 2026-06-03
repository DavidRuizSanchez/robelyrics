# Roadmap pendiente — propuestas (revisión 2026-06-03)

Tareas del backlog que quedan como IDEA/EXPLORACIÓN (no construidas en la sesión
nocturna por ser exploratorias o requerir tu criterio). Cada una con plan concreto.
Lo CONSTRUIDO y desplegado se resume en `data/reference/` y en la memoria del proyecto.

## #16 · Posts de giras (1 por gira)
Datos ya disponibles (de los digests de los libros + research). Giras con material para un post cada una:
- **Pedrá** (gira 1995, Pabellón Real Madrid 5-may-1995, comuna en Durango).
- **La Gira con Platero y Tú** (verano-nov 1995; cierre Palacio Deportes Madrid 8-9 nov → de ahí *Iros todos a tomar por culo*).
- **Moñigos, morid** (1999, Canciones prohibidas; Fito & Fitipaldis de teloneros).
- **Gira 2002** (Yo, minoría absoluta; La Cubierta de Leganés, >20.000).
- **Grandes éxitos y fracasos** (2004; Lleida 14-may → Salamanca 13-nov, 40 ciudades).
- **Robando perchas del hotel** (2012; cierre Recinto Hípico de Cáceres 13-oct, 15.000; primera vez en América).
- **Para todos los públicos** (2014, El Dromedario; España + Latinoamérica).
- **Giras solistas de Robe**: presentación de *Lo que aletea…* (Teatro Romano Mérida etc.), *Mayéutica* ("Ahora es cuando" 2021-22), *Se nos lleva el aire* ("Ni santos ni inocentes" 2024, donde sufrió el tromboembolismo de nov-2024).
**Plan**: generar 1 post evergreen por gira con el blog generator (voz megafan punki) + `context` de los digests, como PROPUESTAS (pending_review) para que las revises antes de publicar. Ambiente de la época + setlist (cuando llegue #22 setlist.fm) + anécdotas reales del libro. Enlazar a discos/lugares/personas implicados.

## #17 · Sección de vídeos oficiales (página por vídeo)
**Plan**: nueva sección `/videos` + `/videos/[slug]`. Fuente: vídeos oficiales (los `youtube_id` canónicos que ya tenemos en `songs` + vídeos de directos/documentales curados). Cada página: embed + ficha (año, director si consta, contexto, producción, significado, participantes) generada con voz del sitio sobre datos verificables. Schema `VideoObject` (ya existe el helper). Distinto de los "vídeos relacionados" (Fase 2) y del vídeo canónico embebido en la canción. Empezar por los vídeos icónicos (So payaso, Jesucristo García, Puta, Esclarecido…) que el libro documenta (director, rodaje).

## #18 · NotebookLM (podcasts, infografías, mapas mentales)
**Uso interno** (alto valor, bajo riesgo): subir el corpus + `data/reference/*.md` a NotebookLM para síntesis, detección de huecos y briefs. **Para publicar** (evaluar derechos): los "Audio Overview" (podcast 2 voces) de NotebookLM son contenido generado por Google — revisar ToS antes de publicarlos; alternativa más limpia y ya decidida en el roadmap: **pipeline propio** (guion GPT + TTS OpenAI 2 voces) con la voz del sitio, que controlamos al 100%. Mapas mentales/infografías de NotebookLM = buenos para uso interno; para la web, generar SVG propios. **Recomendación**: NotebookLM solo como herramienta INTERNA; lo publicable, con pipeline propio.

## #19 · Ranking de mejores canciones (final, "pelotear")
**Ojo no inventar**: no tenemos play-counts ni votos. Opciones honestas:
- (a) Ranking por SEÑAL del corpus: canciones más citadas en fuentes/fan-content (defendible, "las más comentadas").
- (b) Página editorial "Las esenciales" (sin número falso) con criterio declarado.
- (c) **Votación de usuarios** (lo más molón): caja de votos → ranking real con el tiempo. Requiere endpoint + anti-abuso.
**Recomendación**: empezar por (a)+(b) (evergreen "Por dónde empezar / las imprescindibles") y, si gusta, añadir (c). Enlaza con #22 (más tocadas en directo) como señal extra.

## #20 · Consultorio en directo (caja que responde con estilo Robe) — ME GUSTA
**Arquitectura**: RAG sobre el corpus ya vectorizado (Qdrant: `lyrics_full_v1`, `interpretations_v1`, `chunks_v1`) → recupera contexto → LLM con la **voz del sitio** (`build_system_prompt`, megafan punki) responde. El ESTILO importa más que la respuesta (tu nota). Endpoint público `POST /public/ask` con rate-limit (slowapi ya está) + caché de preguntas frecuentes + guardarraíles (solo universo Robe; si no sabe, lo dice con gracia, no inventa). Front: caja en home / página `/pregunta`. **Nombres molones candidatos**: «Pregúntale a la bestia», «El oráculo transgresivo», «Dosis letal de respuestas», «El consultorio del Rey de Extremadura», «Habla con el sol y la nube». **Riesgo**: coste por consulta + abuso → rate-limit + caché + límite de longitud. Prototipable rápido reutilizando el buscador semántico privado.

## #22 · setlist.fm API
**Usos de valor (respetando ToS: atribución + link-back a setlist.fm, sin revender datos)**:
- Histórico de conciertos/setlists por gira → alimenta #16.
- "Canciones más tocadas en directo" → señal para #19 + módulo en ficha de canción ("tocada N veces en directo").
- Datos para páginas de **lugares/salas** (qué se tocó allí).
- Página `/conciertos` o por gira.
**Plan técnico**: cliente con API key (env), cacheo agresivo (los setlists no cambian), ingesta a tabla propia, jobs periódicos. Empezar por importar el histórico de Extremoduro + Robe y derivar "más tocadas".

---
Construido y desplegado esta sesión: voz editorial por tipología, fuentes de autoridad (2 libros + research), ~60 entidades nuevas, /sellos, buscador, tablas técnicas (persona y canción), relacionadas por temas, enlace de fuentes, afín/amigo, fotos. Ver memoria `project_robelyrics_*`.
