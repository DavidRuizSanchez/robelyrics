export const metadata = { title: "Política de cookies · Entre Interiores" };

export default function PoliticaCookies() {
  return (
    <>
      <h1>Política de cookies</h1>
      <p>Última actualización: 6 de mayo de 2026.</p>

      <h2>¿Qué son las cookies?</h2>
      <p>
        Una cookie es un pequeño fichero de texto que un sitio web guarda en
        tu navegador. Permite recordar información sobre tu visita
        (preferencias, estado de sesión) o medir cómo usas el servicio.
      </p>

      <h2>Cookies que usamos</h2>

      <h3>Esenciales (siempre activas, no requieren consentimiento)</h3>
      <ul>
        <li>
          <strong>robelyrics_token</strong>: cookie HttpOnly + Secure +
          SameSite=Lax que contiene tu sesión JWT cuando inicias sesión. Se
          borra al hacer logout o al caducar (7 días). Sin esta cookie no
          puedes acceder a la zona privada — base legal: necesidad técnica
          (RGPD considerando 47).
        </li>
        <li>
          <strong>entreinteriores-cookie-consent</strong>: registra tu
          decisión sobre el banner (&quot;accepted&quot; / &quot;rejected&quot;)
          en localStorage del navegador. No es una cookie técnicamente, pero
          la mencionamos por transparencia.
        </li>
      </ul>

      <h3>Analítica (sólo si aceptas)</h3>
      <ul>
        <li>
          <strong>_ga, _ga_*</strong>: Google Analytics 4. Identifica
          dispositivos de forma anónima para medir audiencia. Caducidad 2
          años. Sólo se cargan si pulsas &quot;Aceptar&quot; en el banner.
        </li>
      </ul>

      <h3>Cookies de terceros embebidos</h3>
      <p>
        Algunos contenidos provienen de terceros que pueden establecer sus
        propias cookies cuando interactúas con ellos:
      </p>
      <ul>
        <li>
          <strong>YouTube</strong> (en páginas de canción que tienen vídeo):
          al reproducir, YouTube puede establecer cookies para preferencias
          y publicidad. Para mitigar usamos el dominio{" "}
          <code>youtube-nocookie.com</code> donde es posible.
        </li>
        <li>
          <strong>Cloudflare</strong>: nuestro CDN puede establecer cookies
          técnicas para detección de bots y rate limiting. No se usan para
          analítica.
        </li>
      </ul>

      <h2>Cómo gestionar tus preferencias</h2>
      <p>
        Cuando visitas el sitio por primera vez mostramos un banner con
        botones <strong>Aceptar</strong> y <strong>Rechazar</strong>. Tu
        elección queda guardada en este navegador.
      </p>
      <p>
        Para cambiar tu decisión, borra el almacenamiento del sitio en tu
        navegador (Chrome:{" "}
        <kbd>
          Configuración → Privacidad → Borrar datos de navegación → Cookies
          y otros datos del sitio
        </kbd>
        ) y recarga. Volverás a ver el banner.
      </p>
      <p>
        En cualquier momento puedes bloquear todas las cookies desde la
        configuración de tu navegador, aunque algunas funciones del sitio
        (como mantener la sesión iniciada) dejarán de funcionar.
      </p>

      <h2>Más información</h2>
      <p>
        Esta política se complementa con nuestra{" "}
        <a href="/legal/privacidad">Política de privacidad</a>. Para cualquier
        consulta, contacta en{" "}
        <a href="mailto:manue@entreinteriores.com">manue@entreinteriores.com</a>.
      </p>
    </>
  );
}
