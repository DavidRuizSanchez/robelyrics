# hola@entreinteriores.com: recibir y mandar sin caer en spam

Objetivo: mandar el outreach desde **hola@entreinteriores.com** (el contacto que ya
publica el footer) en lugar de la Gmail personal, con las respuestas llegando a
davidruizsanchez@gmail.com.

## Estado medido el 07-10-2026

| Qué | Valor | Cómo se ha visto |
|---|---|---|
| MX | `route1/2/3.mx.cloudflare.net` → **Cloudflare Email Routing** | `dig +short MX entreinteriores.com` |
| SPF | `v=spf1 include:_spf.mx.cloudflare.net ~all` | `dig +short TXT entreinteriores.com` |
| DMARC | **no existe** | `dig +short TXT _dmarc.entreinteriores.com` → vacío |
| ¿Ha llegado algún correo a hola@ o manue@? | **ninguno** en la Gmail personal | búsqueda `to:hola@… OR deliveredto:hola@… OR to:manue@…` |

Dos consecuencias:

1. **No hay prueba de que la regla de reenvío exista.** Puede que exista y que nadie
   haya escrito nunca, o puede que no. Hay que mirarlo antes de mandar nada: si un
   periodista contesta y la regla no está, la respuesta se pierde.
2. **Cloudflare Email Routing solo RECIBE.** Para mandar como hola@ hace falta un
   servidor que firme con el dominio.

## Por qué no basta con Gmail «Enviar como» por smtp.gmail.com

Gmail lo permite, pero el correo sale firmado con DKIM `d=gmail.com` y con el
remitente de sobre en gmail.com: **ni SPF ni DKIM quedan alineados con
entreinteriores.com**. Sin DMARC publicado no se rechaza, pero es justo el perfil de
correo frío que los filtros de una redacción mandan a spam. Por eso se usa un relay
que firme con el dominio.

## Pasos (los hace David: no hay credenciales de Cloudflare en el repo)

### 1. Recepción: comprobar la regla
Cloudflare › entreinteriores.com › **Email › Email Routing**:
- Que la pestaña de reglas tenga `hola@entreinteriores.com → davidruizsanchez@gmail.com`
  y esté **Active**. Si no está, «Create address» con esa pareja.
- Que en **Destination addresses** la Gmail aparezca **Verified**.

Prueba: escribir a hola@ **desde otra cuenta** (no desde la misma Gmail: Gmail descarta
la copia reenviada de un correo que tú mismo enviaste y parece que falla).

### 2. Envío: relay SMTP de Brevo (plan gratuito, 300 correos/día)
1. Crear cuenta en brevo.com con hola@entreinteriores.com como remitente.
2. **Senders, Domains & Dedicated IPs › Domains › Add a domain** → entreinteriores.com.
   Brevo da los registros exactos: un TXT `brevo-code:…`, dos CNAME de DKIM
   (`brevo1._domainkey`, `brevo2._domainkey`) y su recomendación de DMARC.
3. Copiar esos registros a Cloudflare › DNS (los CNAME en **DNS only**, nube gris).
4. **SPF**: editar el TXT existente (que solo puede haber uno) para que quede
   `v=spf1 include:_spf.mx.cloudflare.net include:spf.brevo.com ~all`
5. **DMARC** (nuevo TXT en `_dmarc`):
   `v=DMARC1; p=none; rua=mailto:hola@entreinteriores.com`
   Empezar en `none`: no rechaza nada y manda informes. Endurecer a `quarantine` cuando
   los informes enseñen que todo lo legítimo pasa.
6. En Brevo, **SMTP & API › SMTP**: generar una clave SMTP.

### 3. Gmail › Ajustes › Cuentas › «Enviar correo como» › Añadir otra dirección
- Nombre: `David Ruiz · Entre Interiores`. Dirección: `hola@entreinteriores.com`.
  **Desmarcar** «Tratar como alias».
- Servidor SMTP `smtp-relay.brevo.com`, puerto `587`, usuario el login SMTP de Brevo,
  contraseña la clave SMTP, TLS.
- Gmail manda un código a hola@ → llega por la regla del paso 1 (otra prueba de que
  funciona).
- Marcar «Responder desde la misma dirección a la que se envió el mensaje».

### 4. Verificación — no se manda outreach hasta que pase
- `dig +short TXT entreinteriores.com` y `dig +short TXT _dmarc.entreinteriores.com`
  muestran lo nuevo.
- Mandar desde Gmail **como hola@** a la dirección que da **mail-tester.com**:
  nota **≥ 9/10**.
- Mandar a una cuenta de Outlook/Hotmail y mirar las cabeceras
  (`Authentication-Results`): `spf=pass`, `dkim=pass header.d=entreinteriores.com`,
  `dmarc=pass`. Que llegue a Bandeja de entrada, no a Correo no deseado.
- Responder a ese correo desde Outlook y comprobar que la respuesta llega a la Gmail.

## Resultado de la prueba

| Fecha | Prueba | Resultado |
|---|---|---|
| — | regla de reenvío | pendiente |
| — | mail-tester | pendiente |
| — | cabeceras en Outlook | pendiente |
