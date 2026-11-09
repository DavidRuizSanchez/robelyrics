# Fuentes · ANALISIS_REDES.md (v2)

Extraído el 29-10-2026, horas en UTC. La v2 sustituye entera a la v1: se ha rehecho todo desde la fuente.

**Ventana de tráfico:** 2026-09-29 → 2026-10-28, ambos incluidos. En Caddy y en la API de IG va en UTC;
GSC y GA4 usan su propio huso horario, con las mismas fechas.

## Cifras (F-nn)

| ID | Valor | Métrica | Fuente · filtro | Extracción |
|---|---|---|---|---|
| F-01 | 930 (búsqueda Google) · 96 (otros buscadores) · 99 (elperiodicoextremadura.com) | visitas de documento por referer | Log de Caddy en prod (rotados + actual), extraído por ssh. `api/scripts/seo/referers_caddy.py`. Descarta prefetch (`Sec-Purpose`), bots por UA, status ≥ 400, sin referer y referer interno. Google sin Gmail (22), Search Console (4) ni Gemini (1) | 20:51 |
| F-02 | 2.681 / 12.304 / 159 / **2** | reach / views / profile_views / website_clicks | IG Graph API `/{ig}/insights`, `metric_type=total_value`, since 29-09 00:00 → until 29-10 00:00 | 20:52 |
| F-03 | 162 · `http://entreinteriores.com` | followers_count · website | IG Graph API `/{ig}?fields=followers_count,website` | 20:52 |
| F-04 | facebook 17 (7 a /estudios/repertorio-en-directo-extremoduro-robe, 5 a /, 5 a /login) · instagram 3 · threads 2 → **22** | visitas por referer de redes | Igual que F-01 | 20:51 |
| F-05 | 2.302 | prefetch descartado | Igual que F-01 | 20:51 |
| F-06 | 2.971 | documentos sin referer (directo, apps) | Igual que F-01 | 20:51 |
| F-07 | 909 = web 872 + video 19 + image 18 (news 0, discover 0) | clics | GSC `searchAnalytics`, `sc-domain:entreinteriores.com`, `dataState=all`, por `type` (`app/services/gsc_client`) | 20:52 |
| F-08 | google/organic 367 · elperiodicoextremadura.com 56 · ig/social 4 · facebook 0 | sesiones | GA4 propiedad 538152925, `sessionSourceMedium` (`scripts.seo.ga4_social`) | 20:52 |
| F-09 | 711.268 · 89.011 · 14.332 · 4.173 | seguidores en FB: Extremoduro (oficial) · Robe.es · «Extremoduro» (fan) · «Extremoduro A FUEGO» (fan) | `og:description` de /material.defectuoso/, /Robees-1594473607475176, /p/Extremoduro-100045099753805/, /extremoduroafuego/ | 20:53 |
| F-10 | 32.300 | seguidores de @Robe_Extremo, X | HTML de https://x.com/Robe_Extremo | 20:53 |
| F-11 | 214.000 · 43.800 | suscriptores de Robe (UCA_lLfhBYZrUYSf_0s-emfg) · juancaraes | YouTube Data API `channels.statistics` (3 cifras significativas) | 20:53 |
| F-12 | 16.000 | followerCount de @robe_extremo | JSON embebido en https://www.tiktok.com/@robe_extremo | 20:53 |
| F-13 | 23 | suscriptores de @extremoduro_robe | https://t.me/s/extremoduro_robe | 20:53 |
| F-14 | 64 | seguidores de extremoduro.bsky.social | `public.api.bsky.app` `getProfile` | 20:53 |
| F-15 | página «Entre Interiores» (1134563979744417): 0 fans y 0 seguidores; el token no tiene `pages_manage_posts` | — | Graph API `/me/accounts` y `debug_token` (System User «EntreInteriores Bot») | 20:52 |

**Derivadas** (recalculadas desde los datos de arriba): redes = 17 + 3 + 2 = 22. Caddy − GSC = 930 − 909 =
+21 (+2,3 %). GA4 / GSC = 367 / 909 = 40,4 %.

## Discrepancias entre fuentes

- **GA4 frente a GSC y Caddy (Google: 367 frente a 909 y 930; Facebook: 0 frente a 17).** GA4 solo carga
  si se aceptan las cookies (`web/components/ConsentManager.tsx`). Fuente de verdad del volumen: GSC para
  Google y Caddy para el resto. GA4 sirve para comparar consigo mismo y para la calidad.
- **Caddy frente a GSC (+21).** Diferencia de huso horario al cortar el día. No se ha medido.
- **v1 → v2.** La v1 daba 3.433 «visitas desde buscadores» porque contaba el prefetch de Chrome: peticiones
  con `Sec-Purpose: prefetch;anonymous-client-ip` desde el proxy de Google `2001:4860:7…`, que precargan
  resultados de la SERP sin clic. Se detectó al cruzarlo con GSC.

## Afirmaciones (A-nn)

| ID | Afirmación | Cita literal · URL | Comprobado | Veredicto |
|---|---|---|---|---|
| A-01 | Una página de FB puede publicar posts por API | "The pages_manage_posts permission allows your app to create, edit and delete your Page posts." · https://developers.facebook.com/docs/permissions/reference/pages_manage_posts | 20:33 | CONFIRMADA |
| A-02 | Para la página propia basta Standard Access | "Si solo utilizarán tu aplicación usuarios que tienen un rol en ella, los permisos y las funciones que requiere la aplicación solo necesitarán acceso estándar." · https://developers.facebook.com/docs/graph-api/overview/access-levels/ ; App Review: "For apps that needs access to data that you do not own or manage" (URL de A-01) | 20:33 | PARCIAL → **[HIPÓTESIS]** hasta el link post de prueba |
| A-03 | Threads: la tarjeta de enlace solo sale en posts de texto | "This feature is only available for text-only posts." / "Text posts are limited to 500 characters." · https://developers.facebook.com/docs/threads/posts | 20:32 | CONFIRMADA |
| A-04 | X cobra 0,200 $ por post con URL | "Post: Create (with URL)" "$0.200 per request" · https://docs.x.com/x-api/getting-started/pricing | 20:32 | CONFIRMADA |
| A-05 | Los enlaces de un Short no son clicables | "URLs placed in YouTube Shorts comments and Shorts descriptions are non-clickable." · https://support.google.com/youtube/answer/13748639?hl=en | 20:32 | CONFIRMADA |
| A-06 | TikTok: sin auditoría solo `SELF_ONLY`; prohíbe enlaces en el contenido | Lectura del subagente (https://developers.tiktok.com/doc/content-sharing-guidelines), no revalidada por mí | — | NO VERIFICABLE |
| A-07 | Pinterest Trial: pines visibles solo para su creador; Standard pide vídeo | "all Pins and Boards created with Trial access are only visible to their creator as Sandbox entities." / "If you are the only intended user of the Pinterest API, we will still require a video recording of the OAuth flow." · https://developers.pinterest.com/docs/key-concepts/access-tiers/ | 20:32 | CONFIRMADA |
| A-08 | Telegram: el bot publica gratis | "By default, bots are able to message their users at no cost" · https://core.telegram.org/bots/faq | 20:33 | CONFIRMADA |
| A-09 | Bluesky: enlaces y tarjeta por API | Lectura del subagente (https://bsky.network/docs/about-bluesky-content/posts), no revalidada | — | NO VERIFICABLE |
| A-10 | WhatsApp Channels no tiene API de publicación | El subagente no la encontró en la doc de Meta: es ausencia de hallazgo, no prueba | — | NO VERIFICABLE |
| A-11 | Reddit prohíbe el spam por API | Lectura del subagente: "or use the Data APIs to spam…" · https://redditinc.com/policies/data-api-terms, no revalidada | — | NO VERIFICABLE |

A-06, A-09, A-10 y A-11 solo sirven para descartar redes secundarias y no cambian la recomendación.

## Validación final (29-10-2026, 20:51-20:53 UTC)

- **Cruce entre fuentes en la misma ventana:**
  - Google: GSC 909 frente a Caddy 930, delta +2,3 %, cuadra.
  - GA4: 367, el 40 %, explicado por las cookies.
  - F-01, F-02, F-04, F-07 y F-08 se han extraído de nuevo en la v2; ninguna sale de la v1.
- **Audiencias (F-09 a F-14):** releídas en la fuente a las 20:53.
  - Frente a la lectura de las 20:30, solo cambia una: Extremoduro (oficial) pasa de 711.269 a 711.268
    (−1). Se usa la de las 20:53.
  - Las demás, delta 0.
- **No validado:** A-06, A-09, A-10 y A-11, como se indica arriba.
