# Qué red social da tráfico cualificado a Entre Interiores

v2 · 29-10-2026. Criterios de David: **tráfico a la web** y **solo lo que se pueda automatizar**.

Ventana común de todas las mediciones de tráfico: **29-09 → 28-10-2026** (30 días). Cada cifra remite a
[SOURCES.md](SOURCES.md) (`F-nn` = cifra, `A-nn` = afirmación).

> Corrige la v1, que daba 3.433 visitas desde buscadores. 2.302 de ellas eran prefetch de Chrome (Chrome
> precarga los primeros resultados de Google sin que nadie haga clic), no visitas. Ver «Cómo se ha medido».

## Veredicto

1. **Principal: página de Facebook.**
   - Es la única red que ya trae tráfico sin que hagamos nada: 17 visitas sin página propia (F-04).
   - Tiene la mayor audiencia medible del nicho (F-09).
   - Deja enlazar por API (A-01).
   - Usa la misma app de Meta que el circuito de Instagram.
2. **Secundaria: Threads,** solo en posts de texto con tarjeta de enlace (A-03). Va con el mismo stack de
   Meta, pero la audiencia allí no se puede medir.
3. **Descartadas para tráfico automatizado:** X, YouTube Shorts, TikTok, WhatsApp, Telegram, Bluesky,
   Pinterest (por ahora) y Reddit. El motivo de cada una está en la tabla.

**La dosis de realidad, corregida:**
- **Google trajo 930 visitas reales** en 30 días (F-01); Search Console cuenta 909 clics (F-07).
- **Todas las redes juntas trajeron 22** (F-04).

Ninguna red va a sustituir a Google: Facebook es un canal complementario, para llevar el estudio y las
fichas a quien no las busca.

## Lo que pasa hoy (medido)

**Instagram, en la ventana** (F-02, F-03):
- 2.681 cuentas alcanzadas, 12.304 visualizaciones y 159 visitas al perfil;
- **2 toques en el enlace a la web**;
- 162 seguidores.

El contenido gusta, pero la puerta a la web no se abre: es exactamente lo que intuías.

**Visitas reales por origen** (log de Caddy, sin prefetch ni bots, F-01, F-04, F-05):

| Origen | Visitas |
|---|---|
| Búsqueda de Google | 930 |
| Otros buscadores (Bing, DuckDuckGo, Ecosia…) | 96 |
| El Periódico de Extremadura | 99 |
| **Facebook** | **17** (7 al estudio) |
| Instagram | 3 |
| Threads | 2 |

WhatsApp y algunos navegadores dentro de apps no envían referer, así que esa parte del tráfico social cae
en las 2.971 visitas sin referer (F-06) y no se puede atribuir.

## Cómo se ha medido: tres fuentes que ahora cuadran

| Fuente | Google en la ventana | Qué ve |
|---|---|---|
| Search Console (F-07) | **909 clics** (web 872 + vídeo 19 + imagen 18) | Todos los clics desde Google; no depende de cookies |
| Log de Caddy (F-01) | **930 visitas** | Todas las visitas de documento, quitando prefetch, bots y errores |
| GA4 (F-08) | **367 sesiones** | Solo quien acepta las cookies |

- **Caddy frente a GSC: +21 (+2,3 %).** Lo más probable es que sea la ventana: GSC corta el día en hora
  del Pacífico y Caddy en UTC.
- **GA4 ve el 40 % de lo que mide GSC.** Es, aproximadamente, la tasa de aceptación del banner de cookies.
- **Cómo usar cada una:** el volumen se mide con Caddy y GSC; la calidad (interacción, duración, campañas
  UTM), con GA4.

## Comparativa

| Red | Audiencia del nicho (medida) | Enlace clicable por API | Alta | Encaje con el pipeline | Decisión |
|---|---|---|---|---|---|
| **Facebook (página)** | Extremoduro oficial 711.268 · Robe.es 89.011 · fan 14.332 y 4.173 (F-09). Grupos: sin dato | **Sí**, link post (A-01) | Permiso `pages_manage_posts`; Standard Access para la página propia (A-02) **[HIPÓTESIS hasta probarlo]** | Reutiliza Cloudinary, las guardas y la cola | **Principal** |
| **Threads** | NO VERIFICABLE (pide login) | Sí, **solo posts de texto** (A-03) | Invitar a la cuenta como tester | Texto + enlace; los carruseles irían sin tarjeta | **Secundaria** |
| X | Robe oficial 32.300; fan sin dato (F-10) | Sí, a **0,20 $ por post con enlace** (A-04) | Créditos de prepago | Texto + enlace | Fuera: pagas por enlazar y la audiencia es poca |
| YouTube Shorts | Robe 214.000 · juancaraes 43.800 (F-11) | **No**: los enlaces de un Short no son clicables (A-05) | — | Los clips 9:16 encajan | Fuera para tráfico |
| TikTok | Robe oficial 16.000 (F-12) | Prohíbe enlaces en el contenido y, sin auditoría, todo es privado (A-06) | Auditoría | Clips | Fuera |
| Pinterest | NO VERIFICABLE | Sí, el pin lleva enlace | Trial: los pines solo los ve su creador; Standard exige un vídeo de demo (A-07) | Imágenes | Aparcada |
| Telegram | 23 suscriptores en el mayor canal fan (F-13) | Sí, gratis (A-08) | Un bot | Texto + enlace | Fuera: no hay comunidad |
| Bluesky | 64 seguidores en la mayor cuenta fan (F-14) | Sí (A-09) | Basta la cuenta | Texto + enlace | Fuera: no hay comunidad |
| WhatsApp (canales) | — | Sin API de publicación (A-10) | — | — | Fuera |
| Reddit | NO VERIFICABLE | Prohíbe el spam por API (A-11) | — | — | Fuera; además ya está fuera del corpus por política |

## Por qué Facebook, y lo que falta comprobar

**A favor:**
- **Ya funciona sin nosotros.** Alguien compartió el estudio en Facebook y trajo 7 visitas (F-04). Es la
  señal más fiable de que esa audiencia hace clic.
- **La audiencia está ahí.** La página oficial tiene 711.268 seguidores y las fan, 14.332 y 4.173 (F-09).
  Que sea el público que más se parece al nuestro por edad es **[HIPÓTESIS]**: no hay dato demográfico.
- **El coste es bajo.** El System User de la app ya ve la página «Entre Interiores» con permiso para crear
  contenido. Lo que le falta es el scope `pages_manage_posts` (F-15).

**En contra o pendiente:**
- **La página arranca con 0 seguidores** (F-15). Que una página nueva tenga poco alcance orgánico es
  **[HIPÓTESIS]**: no hay dato propio que lo mida.
- **Que baste Standard Access sin App Review es [HIPÓTESIS].** La doc de Meta lo apoya (A-02), pero falta
  probarlo con un link post.
- **La comunidad viva puede estar en los grupos**, cuyos miembros no se pueden leer sin iniciar sesión. No
  se han evaluado.
- **Riesgo compartido.** Que una restricción de Meta a la cuenta de negocio, como la de IG del 24-08,
  alcance también a la página es **[HIPÓTESIS]**: no está comprobado.

## Plan de arranque (no se toca nada sin tu OK)

1. **Permiso y prueba.**
   - Tú: en Business Manager, das al System User acceso a la página y generas un token con
     `pages_manage_posts`.
   - Yo: lo compruebo sin publicar y, con tu OK, publico un link post al estudio con UTM.
2. **Publicar desde la cola de IG.**
   - Cada pieza enlaza a la página de su tema en entreinteriores.com, con
     `utm_source=facebook&utm_medium=social&utm_campaign=<tipo>`.
   - Las noticias sin post propio no se publican.
   - Se reutilizan las imágenes, las guardas y la cola, con un cortacircuitos aparte para que un fallo de
     FB no frene a IG.
3. **Medir a las 4 semanas.**
   - Facebook en Caddy (`scripts/seo/referers_caddy.py`) y en GA4 (`scripts.seo.ga4_social --source
     facebook --campanas`).
   - Se compara contra la línea base de hoy: 17 visitas al mes, sin página propia.

Aparte: la web de la bio de IG está en `http://` (F-03), con un salto de redirección de más.
