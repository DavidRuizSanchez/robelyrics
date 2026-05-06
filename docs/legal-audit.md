# Auditoría legal preparatoria — RobeLyrics ("Entre Interiores")

**Fecha**: 2026-05-01
**Estado del proyecto**: MVP funcional en localhost. NO desplegado.
**Propósito de este documento**: análisis preparatorio para cuando se decida poner la web online. Recoge qué se almacena, bajo qué régimen legal está cada cosa, y qué cambios habría que aplicar según el escenario de despliegue. **No es asesoramiento jurídico profesional**: para un despliegue público con tráfico real, conviene consultar a un abogado especializado en propiedad intelectual y protección de datos en España.

---

## 1. Resumen ejecutivo

El proyecto almacena letras completas (~144 canciones, 6.553 líneas), 323 piezas de fan-content (blogs, foros, transcripts y comentarios de YouTube, anotaciones Genius), un destilado fan por canción (144 filas en `song_interpretations`) y portadas de discos descargadas vía MusicBrainz/Cover Art Archive. Embebe vídeos de YouTube vía iframe oficial (sin descarga salvo para Whisper interno). Hay 1 usuario admin con acceso autenticado.

**Conclusión**: en uso **estrictamente personal** (un solo usuario en localhost) está cubierto. En cuanto se exponga públicamente con registro abierto, aunque sea con auth, hay que cambiar la UI para servir **snippets** (≤4 líneas + link a Genius) en lugar de letras completas, añadir páginas legales (privacy / terms / takedown) y revisar la imagen de cabecera y portadas. Para uso compartido entre familia/amigos cercanos (≤10 usuarios autenticados) hay zona gris jurídica defendible bajo el ámbito doméstico (art. 31.2 LPI), pero conviene mitigar con disclaimer + términos de uso.

---

## 2. Inventario de activos

| Activo | Cantidad | Origen | Storage |
|--------|----------|--------|---------|
| Letras (raw + clean) | 144 canciones / 6.553 líneas | Genius API + scraping fan | `songs.lyrics_*` + `lines.text` |
| Embeddings de líneas | ~6.553 vectores | OpenAI text-embedding-3-large | Qdrant `lines_v1` |
| Embeddings de chunks | ~1.200 vectores | OpenAI | Qdrant `chunks_v1` |
| Embeddings de letras completas | 144 vectores | OpenAI | Qdrant `lyrics_full_v1` |
| Embeddings de interpretaciones | ~3.000 vectores | OpenAI | Qdrant `interpretations_v1` |
| Embeddings de consensus | 144 vectores | OpenAI | Qdrant `consensus_v1` |
| Fan-content | 323 fuentes | Reddit (descartado), foros, blogs, YouTube transcripts/comments, Genius annotations | `interpretation_sources` |
| Destilados fan | 144 | GPT-4o-mini sobre las fuentes | `song_interpretations` |
| Embeds YouTube | 144 videoIds | YouTube Data API (canales Topic) | `songs.youtube_id` |
| Audio descargado | 0 (transitorio) | yt-dlp para Whisper, borrado tras transcripción | — |
| Timestamps (LRC + Whisper) | 134/144 canciones (93%) | lrclib.net + OpenAI Whisper | `lines.start_seconds` |
| Imagen de cabecera | 1 | `robe.es` (sitio oficial) | `web/public/...` (descargada) |
| Portadas de discos | 15 | MusicBrainz Cover Art Archive | `web/public/album-covers/` |
| Datos de usuarios | 1 admin | Self-registered | `users` (email + bcrypt hash + JWT) |
| Logs de queries | Stdout (sin persistencia) | — | — |

---

## 3. Régimen legal por activo

### 3.1 Letras
- **Marco**: Ley de Propiedad Intelectual española (RDLeg 1/1996, "LPI"), arts. 10, 17–25.
- **Titulares**: autores (Robe Iniesta + co-autores Iñaki Antón, etc.) → herederos tras el fallecimiento de Robe (18-10-2025). Plazo de protección: vida del autor + 70 años (art. 26 LPI).
- **Gestión colectiva**: SGAE para la composición; AIE para los derechos de los intérpretes; AGEDI para los productores fonográficos.
- **Genius API ToS** ([genius.com/api-terms](https://genius.com/api-terms)): permite uso no comercial con atribución; **prohíbe redistribución bulk de letras completas**. Almacenarlas es admisible, servirlas masivamente al público no.
- **Conclusión**: storage personal con auth = OK. Servir letras completas a terceros sin licencia = infracción.

### 3.2 Fan-content (blogs, comentarios YT, foros, anotaciones Genius)
- **Marco**: cada pieza es obra autónoma de su autor (LPI art. 10).
- **Cobertura por cita** (LPI art. 32.1): permite reproducir fragmentos de obras ajenas con fines de análisis, comentario o juicio crítico, **siempre con atribución y proporcionado al fin**.
- **Uso transformativo**: el destilado fan agrega/sintetiza ideas, no reproduce textualmente bloques largos. Cumple la doctrina de cita si conserva la atribución (los `source_ids` están guardados y se sirven al usuario).
- **Plataformas**: Reddit ToS (descartado en el corpus por 403). YouTube ToS permite mostrar embeds y leer comentarios públicos vía API oficial. Genius ToS sí permite anotaciones (son CC-BY-NC-SA).
- **Conclusión**: el destilado actual con citation obligatoria es defendible. **Riesgo**: si una fuente tiene licencia más restrictiva (ej. blog con © all rights reserved), el snippet citado debería limitarse a lo mínimo necesario.

### 3.3 Embeds YouTube
- **Marco**: YouTube Terms of Service explícitamente permiten el iframe player (`youtube.com/iframe_api`) sin requerir licencia.
- **Lo que NO está permitido**: descargar audio para servirlo. Whisper se ejecuta sobre archivos transitorios (borrados tras transcripción), lo que técnicamente vulnera el ToS de YouTube ("you shall not download any Content"), aunque el uso sea privado y no haya redistribución del audio.
- **Conclusión**: embed = OK. **Mitigación recomendada para online**: o bien desactivar el pipeline de Whisper antes del despliegue, o documentar que los timestamps existentes se generaron en uso personal.

### 3.4 Imagen de cabecera (descargada de robe.es)
- **Marco**: la web oficial del artista; sin licencia explícita.
- **Riesgo**: bajo en uso personal; medio en sitio fan público no autorizado.
- **Conclusión**: **antes de desplegar online, sustituir por imagen propia o de banco libre** (Unsplash, Pexels, generación AI con licencia comercial).

### 3.5 Portadas de discos
- **Marco**: derechos del diseñador/discográfica (Dro East West, Warner, Sony…).
- **MusicBrainz Cover Art Archive** distribuye covers contribuidas por la comunidad bajo licencia abierta declarada por cada upload (la mayoría CC0 o CC-BY-SA), pero **no garantiza que el uploader tuviera derechos** sobre la imagen original.
- **Cobertura por cita** (LPI art. 32): mostrar la portada como ilustración de la entrada del álbum (función referencial, no decorativa) tiene amparo doctrinal en uso editorial/comentario.
- **Conclusión**: aceptable en sitio fan editorial. **Recomendación para online**: revisar la licencia declarada por cover en CAA y reemplazar las que tengan licencia restrictiva.

### 3.6 Datos personales (usuarios)
- **Marco**: RGPD (UE 2016/679) + LOPDGDD (LO 3/2018).
- **Aplica si**: el sitio es accesible desde la UE (lo será si despliega en Hetzner/Contabo en Alemania).
- **Datos almacenados**: email, password hash (bcrypt cost 12), token JWT (HS256, TTL 30 días).
- **Necesario para online**: política de privacidad, base legal del tratamiento (consentimiento), derechos ARCO (acceso/rectificación/cancelación/oposición + portabilidad/limitación), procedimiento de baja, encargado de tratamiento si hubiera.
- **Datos sensibles**: ninguno (no hay categorías especiales del RGPD).

### 3.7 Logs y telemetría
- Actualmente no se persisten queries de búsqueda ni IPs. Si se añadieran (analytics), entrarían bajo RGPD.

---

## 4. Análisis por escenario de despliegue

### Escenario A — Personal/privado en localhost (ESTADO ACTUAL)
**Diagnóstico**: cumple. Auth garantiza que solo el usuario accede. La copia privada de letras compradas/streameadas está cubierta por art. 31.2 LPI.

**Cambios necesarios**: ninguno.

---

### Escenario B — Compartir con familia/amigos cercanos (≤10 usuarios autenticados, registro cerrado)
**Diagnóstico**: zona defendible bajo "ámbito estrictamente doméstico" (art. 31.2 LPI), aunque la jurisprudencia es ambigua sobre dónde acaba lo doméstico cuando hay servidor en internet.

**Recomendaciones**:
- [ ] Disclaimer en footer: *"Sitio fan no oficial · Letras © sus autores · Uso privado entre amigos"*.
- [ ] Página `/sobre` explicando el régimen del proyecto.
- [ ] Términos de uso simples (qué es, quién lo opera, cómo se usa).
- [ ] Política de privacidad mínima (qué datos guarda, contacto).
- [ ] **Registro cerrado por invitación** (pre-creación de usuarios; deshabilitar self-signup si lo hubiera).
- [ ] Robots.txt: `Disallow: /` para evitar indexación.
- [ ] No publicar la URL en redes públicas / SEO.
- [ ] Cambiar imagen de cabecera a propia o stock libre.

---

### Escenario C — Público con auth pero registro abierto
**Diagnóstico**: zona gris alta. Servir letras completas a usuarios anónimos registrados es funcionalmente equivalente a redistribuir letras, lo que SGAE/Warner pueden exigir licenciar.

**Cambios obligatorios**:
- [ ] **Pasar de letras completas a snippets ≤4 líneas + link a Genius** (cita art. 32 LPI). Pierde experiencia karaoke, pero cumple. Implementación: el endpoint `/songs/{slug}` deja de devolver `lines` completas; sirve solo el `matched_line + ±2 contexto` para resultados de búsqueda.
- [ ] Alternativa: licenciar con SGAE + AIE + AGEDI (carísimo y poco realista para proyecto personal).
- [ ] Política de privacidad + términos de uso + cookies banner (RGPD/LSSI-CE).
- [ ] Procedimiento DMCA / takedown (LSSI-CE art. 16): email `legal@<dominio>` que reciba reclamaciones, eliminar contenido afectado en <72h, registrar la reclamación.
- [ ] Disclaimer prominente: *"Letras © sus autores · Sitio fan no oficial · No afiliado con Robe Iniesta, Extremoduro, ni sus discográficas"*.
- [ ] **Logos y nombre**: el "Sol & Nube" + "Entre Interiores" están a salvo (no son marcas registradas que conflicten). Los nombres "Extremoduro" / "Robe Iniesta" en metadata son referencia descriptiva (uso nominativo lícito).
- [ ] Imagen de cabecera: cambiar a propia.
- [ ] Revisar licencia individual de cada portada de disco en Cover Art Archive.
- [ ] Whisper: documentar que los timestamps se generaron en uso personal pre-despliegue, o eliminar el pipeline.
- [ ] HTTPS obligatorio (HSTS), cookies con `Secure: true`.

---

### Escenario D — Comercial (suscripción, ads, etc.)
**Diagnóstico**: requiere licencia ineludible con SGAE/AIE/AGEDI. Fuera del alcance razonable de un proyecto personal.

---

## 5. Recomendaciones técnicas para "online con auth" (Escenario C)

Si llegado el momento se decide ir a este escenario, estos son los cambios concretos en el código:

### 5.1 UI: snippet en lugar de letra completa
- `web/app/[artist]/[album]/[song]/page.tsx`: ocultar la sección "verso a verso" o limitar a las 4 líneas centrales del *match* + link "Ver completa en Genius".
- `web/components/SemanticResultCard.tsx`: ya muestra snippet (matched_line + context_before/after limitado a 1-2). OK.
- `web/components/CompleteResultCard.tsx`: limita `continuation_lines` a 3 max.
- Backend `api/app/routers/catalog.py`:
  - `/songs/{slug}` deja de devolver `lines` completas; o bien devuelve solo metadatos + `genius_url` para redirigir al usuario.
  - Mantener `/search/semantic` y `/search/complete` con snippets cortos.
- `KaraokePlayer`: no aplicable si no hay letras completas. Desactivar o eliminar.

### 5.2 Páginas legales
- `/legal/privacy`: política de privacidad RGPD.
- `/legal/terms`: términos de uso.
- `/legal/takedown`: procedimiento para reclamaciones.
- Footer con enlaces a las tres + email de contacto.

### 5.3 Cookies
- Banner de cookies (CMP simple, ej. `react-cookie-consent`).
- Cookies actuales: `robelyrics_token` (esencial, no requiere consentimiento). Si se añaden analytics, requieren consent.

### 5.4 Imagen y portadas
- Cambiar `web/public/header-image.jpg` (o equivalente) a imagen propia o Unsplash con licencia.
- Auditar cada `web/public/album-covers/*.jpg`: contrastar con Cover Art Archive y reemplazar las problemáticas por placeholder genérico.

### 5.5 Robots / SEO
- Si se quiere visibilidad en buscadores: `robots.txt` permisivo + sitemap.
- Si se prefiere bajo perfil: `Disallow: /` + meta `noindex`.

---

## 6. Acciones inmediatas previas al primer deploy

Cuando se decida el deploy, ejecutar este checklist **antes** de exponer la web:

- [ ] Decidir escenario (B, C o D) y aplicar el conjunto de cambios correspondiente.
- [ ] Crear `web/app/legal/privacy/page.tsx`, `web/app/legal/terms/page.tsx`, `web/app/legal/takedown/page.tsx`.
- [ ] Footer con enlaces legales + disclaimer + email contacto.
- [ ] Sustituir imagen de cabecera por propia/libre.
- [ ] Auditar licencia de las 15 portadas (script: comprobar `release-group/{mbid}` en CAA y registrar la licencia declarada).
- [ ] Email registrado para takedowns (ej. `legal@<dominio>` configurado en el DNS del dominio).
- [ ] HTTPS obligatorio (Caddy/Traefik con cert Let's Encrypt automático).
- [ ] Cookies: `Secure: true` y `SameSite=lax` en producción (`web/lib/auth.ts` ya tiene comentario `// local; en producción true`).
- [ ] HSTS header en el reverse proxy.
- [ ] Robots.txt según escenario.
- [ ] Backup automatizado de Postgres (los datos del corpus son irreproducibles si se pierden).
- [ ] Si va a Hetzner/Contabo (servidores en UE): registro como Responsable de Tratamiento ante AEPD si los usuarios > esfera doméstica.
- [ ] Consultar a un abogado especializado **antes de abrir registro público**.

---

## 7. Riesgos no resueltos

- **MusicBrainz / CAA portadas**: la licencia declarada por cada upload no garantiza que el uploader tuviera derechos. Riesgo bajo (la jurisprudencia tolera el uso ilustrativo en sitios editoriales fan), pero no nulo.
- **Whisper sobre audio de YouTube**: aunque el archivo se borra tras la transcripción, descargarlo viola el ToS de YouTube. El uso fue puntual y privado; documentado por si se cuestiona.
- **Reddit fan-content**: actualmente 403 bloquea la ingesta automática. Las pocas piezas de Reddit que pudieran haberse ingestado están bajo la licencia automática de Reddit (CC-BY-NC-SA limitada al sitio); su uso fuera de Reddit es ambiguo.
- **Snippets vs letra completa**: la doctrina de cita exige proporcionalidad ("la extensión necesaria al fin"). Cuatro líneas centrales del *match* es razonable; servir la letra entera no.
- **Adaptación tras fallecimiento del autor**: los herederos pueden ejercer derechos morales (paternidad, integridad) durante 70 años. El destilado fan, en tanto interpreta intenciones, tiene un componente reputacional que conviene mantener riguroso (citas obligatorias, fan_consensus marcado como tal y no como "voz oficial").

---

## 8. Notas finales

Este documento se debe actualizar:
1. Antes de desplegar online (revisar checklist sec. 6).
2. Cuando cambien las leyes aplicables (atención: Reglamento DSA UE entró en vigor 2024; LPI puede modificarse).
3. Cuando se añadan nuevos tipos de fuente (TikToks, podcasts, etc.).
4. Si SGAE/AIE/AGEDI o herederos contactaran requiriendo licencia o takedown.

**Contacto autor del proyecto**: davidruizsanchez@gmail.com
**Naturaleza del proyecto**: fan, no comercial, no afiliado.
