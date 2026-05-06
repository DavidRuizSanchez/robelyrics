/**
 * Serializa un objeto JSON-LD de forma segura para inyectarlo en un
 * <script type="application/ld+json"> con dangerouslySetInnerHTML.
 *
 * Sin escapar `<`, un valor que contenga `</script>` cerraría el bloque
 * y permitiría XSS. Reemplazar `<` por `<` mantiene el JSON válido
 * y rompe la secuencia de cierre, sin afectar a parsers de schema.org.
 */
export function safeJsonLd(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}
