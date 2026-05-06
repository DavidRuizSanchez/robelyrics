export const metadata = { title: "Política de privacidad · Entre Interiores" };

export default function PoliticaPrivacidad() {
  return (
    <>
      <h1>Política de privacidad</h1>
      <p>Última actualización: 6 de mayo de 2026.</p>

      <h2>Responsable del tratamiento</h2>
      <p>
        David Ruiz Sánchez, persona física residente en España. Contacto:{" "}
        <a href="mailto:hola@entreinteriores.com">hola@entreinteriores.com</a>.
        En este sitio no existe Delegado de Protección de Datos (DPD)
        designado por no ser obligatorio en proyectos de esta naturaleza,
        pero el responsable atiende personalmente las consultas.
      </p>

      <h2>Datos que se tratan y finalidades</h2>

      <h3>1. Registro y autenticación</h3>
      <p>
        Cuando creas una cuenta, almacenamos tu <strong>email</strong> y un{" "}
        <strong>hash bcrypt</strong> de tu contraseña (no la contraseña en
        claro, no se puede recuperar). Finalidad: permitirte acceder a la
        zona privada del cancionero. Base jurídica: ejecución del servicio
        gratuito que solicitas.
      </p>

      <h3>2. Aceptación de términos</h3>
      <p>
        Registramos la <strong>versión de los términos aceptada</strong>, la{" "}
        <strong>dirección IP</strong> desde la que se aceptaron, el user-agent
        y el momento. Finalidad: cumplir con la obligación probatoria del
        consentimiento informado (RGPD art. 7.1).
      </p>

      <h3>3. Verificación de email y reseteo de contraseña</h3>
      <p>
        Generamos tokens de un solo uso con caducidad corta (24 h
        verificación, 30 min reseteo). En el flujo de reseteo guardamos
        además la IP solicitante para auditoría ante abusos. Los tokens se
        invalidan al consumirse o al solicitar uno nuevo.
      </p>

      <h3>4. Analítica anónima (Google Analytics 4)</h3>
      <p>
        Si pulsas <strong>&quot;Aceptar&quot;</strong> en el banner de
        cookies, cargamos Google Analytics 4 con identificador{" "}
        <code>G-TSTB5HVWNT</code>. La señal recogida incluye: páginas
        visitadas, dispositivo, navegador, país aproximado y duración de
        sesión. <strong>No se recogen datos personales identificables</strong>
        : la IP se anonimiza, no se cruza con tu cuenta y los identificadores
        de cliente son aleatorios. Si pulsas &quot;Rechazar&quot; o no
        respondes, GA4 <strong>no se carga</strong>. Base jurídica:
        consentimiento (RGPD art. 6.1.a, ePrivacy).
      </p>

      <h3>5. Logs operacionales</h3>
      <p>
        El servidor mantiene logs cortos (30 días) con IPs y rutas de
        peticiones, exclusivamente para detectar abusos y depurar errores.
        No se cruzan con tu cuenta y no se ceden a terceros. Base jurídica:
        interés legítimo del responsable en la seguridad del servicio.
      </p>

      <h2>Plazos de conservación</h2>
      <ul>
        <li>Cuenta y email: hasta que solicites su borrado.</li>
        <li>Tokens de verificación / reseteo: hasta su consumo o caducidad.</li>
        <li>Logs operacionales: 30 días desde su generación.</li>
        <li>Datos analíticos GA4: según la retención por defecto de Google (2 meses para datos de usuario).</li>
      </ul>

      <h2>Destinatarios y encargados de tratamiento</h2>
      <ul>
        <li>
          <strong>Hetzner Online GmbH</strong> (Alemania): hosting del
          servidor (DPA estándar UE).
        </li>
        <li>
          <strong>Cloudflare, Inc.</strong> (EE.UU.): CDN y DNS, con cláusulas
          contractuales tipo aprobadas por la Comisión Europea.
        </li>
        <li>
          <strong>Google LLC</strong> (EE.UU.): Google Analytics, sólo si das
          consentimiento. Adhesión al Data Privacy Framework UE-EE.UU.
        </li>
        <li>
          <strong>Gmail SMTP</strong> (Google): para enviar correos
          transaccionales (verificación, reseteo). En el futuro se migrará a
          Resend con dominio propio.
        </li>
      </ul>

      <h2>Tus derechos</h2>
      <p>
        Como titular de los datos, puedes ejercer en cualquier momento los
        derechos de <strong>acceso, rectificación, supresión, oposición,
        limitación y portabilidad</strong> escribiendo a{" "}
        <a href="mailto:hola@entreinteriores.com">hola@entreinteriores.com</a>{" "}
        desde la dirección registrada en tu cuenta. La solicitud se atiende
        en un plazo máximo de un mes.
      </p>
      <p>
        Si consideras que el tratamiento no se ajusta a la normativa, puedes
        presentar una reclamación ante la <strong>Agencia Española de
        Protección de Datos</strong> (
        <a href="https://www.aepd.es" target="_blank" rel="noreferrer">
          www.aepd.es
        </a>
        ).
      </p>

      <h2>Menores</h2>
      <p>
        El servicio no está dirigido a menores de 16 años (umbral del
        consentimiento digital en España, art. 7.1 LOPDGDD). Si detectamos
        una cuenta de un menor, la suspenderemos.
      </p>

      <h2>Cambios en esta política</h2>
      <p>
        Si modificamos esta política sustancialmente, lo notificaremos por
        email a los usuarios registrados y publicaremos el cambio en esta
        misma página, con fecha de actualización en cabecera.
      </p>
    </>
  );
}
