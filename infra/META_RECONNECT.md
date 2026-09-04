# Reconexión de Instagram a una app de Meta propia (Entre Interiores)

Objetivo: dejar de depender de la app **AdrenalynTracker** y publicar en
**@entreinterioresrobe** desde una app de Meta **independiente**, bajo la
cuenta de **Pepe Botika**, con un **token que no caduca** (System User).

> Por qué hace falta esto: la Graph API nunca habla directa con Instagram.
> Necesita la cadena **Usuario de FB → Página de FB → cuenta IG Business**.
> Hoy el token de AdrenalynTracker solo ve la Página "Adrenalyn Card Tracker"
> (→ @adrenalyntrackerpro). @entreinterioresrobe no cuelga de ninguna Página
> que esa app/usuario administre, por eso falla con "Object does not exist".

---

## Resumen de lo que vas a conseguir (4 valores a copiar al final)

Al terminar tendrás que pasarme estos 4 datos; yo los meto en
`/opt/robelyrics/.env` y recreo el contenedor:

| Variable | Qué es |
|----------|--------|
| `META_APP_ID` | ID de la app nueva |
| `META_APP_SECRET` | Secreto de la app nueva |
| `INSTAGRAM_ACCOUNT_ID` | ID numérico del IG Business de @entreinterioresrobe |
| `INSTAGRAM_ACCESS_TOKEN` | Token de System User (sin caducidad) |

---

## FASE 0 · Ver dónde estamos (5 min, desde el móvil)

En la app de **Instagram**, con la sesión de @entreinterioresrobe:

1. **Configuración → Cuenta → Cambiar a cuenta profesional** (si no lo es ya).
   Elige **Empresa** (Business), no Creador — Business es lo que admite la
   Graph API de publicación.
2. Anota si ya está **vinculada a una Página de Facebook**:
   Configuración → **Centro de cuentas** o Editar perfil → "Página".
   - Si ya hay una Página vinculada y la administra Pepe Botika → genial,
     reutilizamos esa (saltas la Fase 1).
   - Si no hay Página, o la administra otra cuenta → Fase 1.

---

## FASE 1 · Página de Facebook (si no existe)

La cuenta IG Business **debe** colgar de una Página de FB que administre
Pepe Botika.

1. Con sesión de **Pepe Botika** en Facebook, crea una Página:
   👉 https://www.facebook.com/pages/create
   Nombre sugerido: **Entre Interiores**. Categoría: "Músico/banda" o
   "Sitio web de noticias y medios". No hace falta rellenarla a fondo.
2. Vincula el Instagram a esa Página:
   Página → **Configuración** → **Cuentas vinculadas** (o "Centro de cuentas")
   → **Instagram** → Conectar → entra con @entreinterioresrobe.
   👉 https://www.facebook.com/settings/?tab=linked_instagram

---

## FASE 2 · Portfolio de negocio (Meta Business)

Necesitamos un "Business portfolio" para crear el System User y agrupar los
activos (Página + IG + App).

1. Entra a **Meta Business Suite / Configuración del negocio** con Pepe Botika:
   👉 https://business.facebook.com/settings
2. Si te pide crear un **portfolio de negocio**, créalo (nombre: "Entre
   Interiores"). Si Pepe Botika ya tiene uno (el del tracker), puedes usar el
   mismo — la independencia la da la **app**, no el portfolio.
3. Añade los activos a ese portfolio:
   - **Cuentas → Páginas → Añadir → Añadir una página** → la Página de la Fase 1.
   - **Cuentas → Cuentas de Instagram → Añadir** → @entreinterioresrobe.

---

## FASE 3 · Crear la app de Meta NUEVA e independiente

1. Ve a tus apps de desarrollador (sesión de Pepe Botika):
   👉 https://developers.facebook.com/apps/
2. **Crear app**.
3. Caso de uso / tipo: elige **"Otros"** → tipo de app **"Empresa" (Business)**.
   (Si te muestra el flujo nuevo por "casos de uso", elige el que incluya
   **Instagram** / "Acceso a la API de Instagram".)
4. Nombre: **Entre Interiores** (o "EntreInteriores Publisher"). Asóciala al
   **portfolio de negocio** de la Fase 2.
5. Una vez creada, en **Configuración → Información básica**:
   👉 anota el **Identificador de la app** (`META_APP_ID`) y, pulsando
   "Mostrar", el **Clave secreta de la app** (`META_APP_SECRET`).

### 3b · Añadir el producto Instagram

6. En el panel de la app, **Añadir producto** → **Instagram** →
   **Configurar** (la variante "con inicio de sesión de Facebook" /
   *Instagram API with Facebook Login*, porque publicamos vía
   `graph.facebook.com`).
7. No necesitas "App Review" para publicar en TU PROPIA cuenta: mientras la
   app esté en **modo desarrollo** y Pepe Botika tenga rol en ella y sea dueño
   de los activos, los permisos funcionan. (El System User de la Fase 4 lo
   hace aún más robusto, independiente del modo.)

---

## FASE 4 · Token de System User (NO caduca) — la pieza clave

Esto te da un token de servidor que no expira, ideal para el cron.

1. En **Configuración del negocio**:
   👉 https://business.facebook.com/settings/system-users
2. **Usuarios → Usuarios del sistema → Añadir**. Nombre: "EntreInteriores Bot".
   Rol: **Administrador**.
3. Selecciónalo → **Asignar activos**:
   - La **Página** (Entre Interiores) → permiso **Control total**.
   - La **cuenta de Instagram** (@entreinterioresrobe) → control total.
   - La **app** (Entre Interiores) → acceso.
4. **Generar nuevo token**:
   - App: la app nueva.
   - **Caducidad del token: Nunca**.
   - Permisos (marca estos 6):
     `instagram_basic`, `instagram_content_publish`,
     `pages_show_list`, `pages_read_engagement`, `business_management`,
     `instagram_manage_insights`.

   > ⚠️ `instagram_manage_insights` faltaba en el token generado en su día y
   > por eso **cualquier LECTURA de datos falla con `(#10) Application does not
   > have permission for this action`**: tanto los insights de la propia cuenta
   > como `business_discovery` (estudiar qué publican otras cuentas). Publicar
   > sí funcionaba, porque eso solo necesita `instagram_content_publish`.
   - **Generar** → copia el token YA (solo se muestra una vez) → ese es
     `INSTAGRAM_ACCESS_TOKEN`.

---

## FASE 5 · Sacar el INSTAGRAM_ACCOUNT_ID

Con el token recién creado, abre el explorador o pega esta URL en el navegador
(sustituyendo `TU_TOKEN`):

```
https://graph.facebook.com/v21.0/me/accounts?fields=name,instagram_business_account{username,id}&access_token=TU_TOKEN
```

👉 Explorador (alternativa visual): https://developers.facebook.com/tools/explorer/

Busca el bloque cuyo `name` es tu Página "Entre Interiores". Dentro,
`instagram_business_account.id` (con `username: entreinterioresrobe`) es tu
**`INSTAGRAM_ACCOUNT_ID`**.

Verifica que es alcanzable (debe devolver 200 con el username):
```
https://graph.facebook.com/v21.0/ESE_ID?fields=username,followers_count,media_count&access_token=TU_TOKEN
```

---

## FASE 6 · Conectar en producción (esto lo hago yo)

Me pasas los 4 valores y yo:
1. Actualizo `/opt/robelyrics/.env` (`META_APP_ID`, `META_APP_SECRET`,
   `INSTAGRAM_ACCOUNT_ID`, `INSTAGRAM_ACCESS_TOKEN`).
2. Recreo el contenedor `api`.
3. Corro el health check real (lectura del IG) + un `publish_next --dry-run`.
4. Calentamos la cuenta despacio (1-2 posts/día los primeros días) antes de
   abrir la cadencia, para no disparar el antibot de Meta.

---

## Enlaces de referencia

- Apps de desarrollador: https://developers.facebook.com/apps/
- Configuración del negocio: https://business.facebook.com/settings
- Usuarios del sistema: https://business.facebook.com/settings/system-users
- Explorador de la Graph API: https://developers.facebook.com/tools/explorer/
- Depurador de tokens: https://developers.facebook.com/tools/debug/accesstoken/
- Docs publicación IG: https://developers.facebook.com/docs/instagram-platform/content-publishing

## Trampas conocidas (no tropezar)

- **No publiques 3+ posts el primer día por API**: el antibot de Meta
  restringe cuentas IG nuevas/recién enlazadas que auto-publican rápido
  (fue la causa probable del problema original). Calentar despacio.
- **El token de System User no caduca**, pero si revocas permisos o cambias
  el rol del usuario del sistema, deja de funcionar.
- **App en modo desarrollo** basta para tu propia cuenta; no hace falta App
  Review mientras no publiques en cuentas de terceros.

---

## Cuenta restringida (`code 25 / subcode 2207050`)

**Síntoma**: la web va bien, el panel enseña la cuenta en verde, pero el feed
lleva días sin moverse y los items de la cola traen
`{'message': 'User access is restricted', 'code': 25, 'error_subcode': 2207050}`.

**Qué lo provoca** (caso real del 24-ago-2026): un **inicio de sesión desde una
ubicación inusual**. El titular estaba de vacaciones y entró a la cuenta desde
Pontevedra; Meta lo tomó por acceso sospechoso y restringió la cuenta. No tuvo
nada que ver con el ritmo de publicación ni con la API. Se resolvió entrando a
la cuenta y confirmando «he sido yo».

Así que lo PRIMERO que hay que mirar ante un 25/2207050 es si alguien accedió
hace poco desde otro sitio (viaje, VPN, móvil nuevo). Es lo más probable y se
arregla en dos clics.

**Qué NO es** (comprobado durante el incidente del 24-ago-2026, todo con GETs):

| Comprobación | Resultado con la cuenta restringida |
|---|---|
| `debug_token` | `is_valid: true`, sin caducidad, con `instagram_content_publish` |
| `GET /{ig-id}?fields=username,...` | responde con normalidad |
| `GET /{ig-id}/content_publishing_limit` | `quota_usage: 0` de 100 |
| `GET /me/accounts` | el vínculo Página↔IG, intacto |

O sea: **no es el token, ni la cuota, ni el enlace con la Página**. Leer funciona;
lo único bloqueado es publicar. Y no hay forma de detectarlo con una lectura: el
IG Graph API no expone Account Quality. La única prueba fiable es intentar crear
un container.

**Cómo se comprueba a mano** (crea un borrador, NO publica; caduca solo en 24 h):

```bash
ssh robelyrics
cd /opt/robelyrics
TOK=$(grep -m1 '^INSTAGRAM_ACCESS_TOKEN=' .env | cut -d= -f2-)
IGID=$(grep -m1 '^INSTAGRAM_ACCOUNT_ID=' .env | cut -d= -f2-)
curl -s -X POST "https://graph.facebook.com/v21.0/$IGID/media" \
  -d "image_url=https://res.cloudinary.com/demo/image/upload/w_1080,h_1080,c_fill/sample.jpg" \
  -d "access_token=$TOK"
```

Si devuelve un `{"id": ...}`, se puede publicar. Si devuelve el 25/2207050, sigue
restringida.

**Cómo se arregla**: solo a mano, y no desde la app del móvil. Entra en
<https://www.instagram.com/> **desde el navegador** con `@entreinterioresrobe` y
completa lo que pida: Configuración → Estado de la cuenta (Account Quality),
verificación de identidad, fecha de nacimiento o la apelación que haya abierta.

**Qué hace el sistema solo mientras tanto**:

1. `errors.quema_intento` reconoce el 25/2207050 como GLOBAL y **no le gasta
   intentos a ningún post** (ver la sección de `CLAUDE.md`).
2. El cortacircuitos (`publisher.publicacion_bloqueada`) para al cron para no
   subir imágenes a Cloudinary ni crear publicaciones que Meta va a rechazar.
   Caduca solo cada `IG_BLOCK_WINDOW_H` (6 h) y el siguiente intento real hace
   de sondeo: en cuanto Meta levante el bloqueo, se reanuda sin tocar nada.
3. `scripts.instagram.notify_health` (cron 09:20 UTC) manda un correo el primer
   día, y vuelve a sonar al escalar de tramo (2/4/7/14/30 días).

**Después de que se levante**, para recuperar lo que se quedó sin intentos:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T api \
  python -m scripts.instagram.recover_failed --dry-run
# revisar el reparto y entonces:
  ... python -m scripts.instagram.recover_failed --apply --limit 4
```

Va por tandas a propósito: devolver toda la cola de golpe activa el modo atasco
(un post cada 10 h → ~17/semana) y reanudar a ese ritmo justo después de una
restricción es la peor forma de estrenar la cuenta. Es idempotente: se repite
cuando la cola baje.
