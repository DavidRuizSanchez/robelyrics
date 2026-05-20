export const metadata = { title: "Atribuciones y créditos · Entre Interiores" };

export default function Atribuciones() {
  return (
    <>
      <h1>Atribuciones y créditos</h1>
      <p>Última actualización: 6 de mayo de 2026.</p>

      <p>
        Entre Interiores no existiría sin el trabajo de muchas personas y
        proyectos. Esta página recoge las atribuciones que la convención
        editorial general no permite incluir en cada artículo.
      </p>

      <h2>Letras de canciones</h2>
      <p>
        Las letras citadas pertenecen a sus autores y a las editoriales que
        gestionan los derechos. Se citan parcialmente bajo derecho de cita
        (LPI art. 32) con fines de análisis y comentario. La fuente
        principal es{" "}
        <a href="https://genius.com" target="_blank" rel="noreferrer">
          Genius
        </a>
        ; en cada página de canción enlazamos al original para consultar la
        letra completa.
      </p>

      <h2>Análisis fan</h2>
      <p>
        Los textos de análisis, contexto e interpretación que se muestran en
        la zona privada del cancionero proceden de comunidades de fans y
        creadores que han escrito sobre la obra de Robe a lo largo de los
        años (foros, blogs, vídeos, papers académicos). Se redistribuyen
        bajo licencia{" "}
        <a
          href="https://creativecommons.org/licenses/by-nc-sa/3.0/"
          target="_blank"
          rel="noreferrer"
        >
          Creative Commons BY-NC-SA 3.0
        </a>
        , con atribución explícita en cada cita y enlace a la fuente
        original.
      </p>
      <p>
        Para una lista detallada por canción, consulta cada página dentro
        del área privada (
        <a href="/biblioteca/atribuciones">Atribuciones</a> en /biblioteca).
      </p>

      <h2>Vídeos embebidos</h2>
      <p>
        Algunas páginas integran vídeos de YouTube vía iframe oficial. Cada
        vídeo pertenece a su creador y se respetan sus términos de servicio.
        Cuando es posible se utiliza el dominio{" "}
        <code>youtube-nocookie.com</code>.
      </p>

      <h2>Tipografías</h2>
      <ul>
        <li>
          <strong>Spectral</strong> · Production Type / Google Fonts (SIL
          OFL). Cabeceras y cuerpo serif.
        </li>
        <li>
          <strong>JetBrains Mono</strong> · JetBrains s.r.o. (SIL OFL).
          Etiquetas, códigos y números.
        </li>
        <li>
          <strong>Caveat</strong> · Pablo Impallari (SIL OFL). Detalles
          ornamentales.
        </li>
      </ul>

      <h2>Tecnologías y servicios</h2>
      <ul>
        <li>
          <strong>Next.js</strong>, <strong>React</strong>,{" "}
          <strong>Tailwind CSS</strong> · frontend.
        </li>
        <li>
          <strong>FastAPI</strong>, <strong>SQLAlchemy</strong>,{" "}
          <strong>PostgreSQL</strong>, <strong>Qdrant</strong> · backend y
          búsqueda.
        </li>
        <li>
          <strong>OpenAI</strong> (text-embedding-3-large + GPT-4o-mini) ·
          embeddings semánticos y reranking de resultados.
        </li>
        <li>
          <strong>Caddy</strong> · reverse proxy con TLS automático.
        </li>
        <li>
          <strong>Hetzner Cloud</strong> · infraestructura.
        </li>
        <li>
          <strong>Cloudflare</strong> · DNS, CDN.
        </li>
      </ul>

      <h2>Iconografía</h2>
      <p>
        Los símbolos &quot;Sol &amp; Nube&quot; y el delfín ornamental son
        guiños al tatuaje de Robe, redibujados como interpretación
        editorial propia, sin pretensión de calcar marcas registradas.
      </p>

      <h2>Inspiración editorial</h2>
      <p>
        El proyecto se inspira en cancioneros literarios y revistas de
        crítica musical impresa, con el objetivo de honrar la obra de Robe
        desde el respeto y la contemplación, no desde la mercadotecnia.
      </p>

      <h2>Errores u omisiones</h2>
      <p>
        Si encuentras un error de atribución o eres autor de un contenido
        citado y prefieres otra forma de aparecer (o no aparecer), escríbenos
        a{" "}
        <a href="mailto:manue@entreinteriores.com">manue@entreinteriores.com</a>{" "}
        y lo corregimos lo antes posible.
      </p>
    </>
  );
}
