#!/bin/bash
# Vigilancia de la migración a gpt-6-luna (deploy del 19-10-2026 09:57:45 UTC).
# Lee el log de cron de prod desde un instante y resume las llamadas a OpenAI
# por código HTTP, los errores de parámetros y los tracebacks. Solo lectura.
#
# Uso: bash infra/local/check_openai_migration.sh ["2026-10-19 09:57:45"]
set -u
SINCE="${1:-2026-10-19 09:57:45}"

ssh robelyrics "bash -s -- '$SINCE'" <<'REMOTE'
SINCE="$1"
LOG=/var/log/robelyrics-cron.log
# Las líneas de log empiezan por "YYYY-MM-DD HH:MM:SS"; las que no (tracebacks)
# heredan la marca de la última línea con fecha.
{ zcat -f "$LOG.1" 2>/dev/null; cat "$LOG"; } | awk -v since="$SINCE" '
  /^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]{8}/ { ts = substr($0, 1, 19) }
  ts >= since { print }
' > /tmp/openai_check_window.log

echo "== Ventana: desde $SINCE UTC hasta $(date -u '+%Y-%m-%d %H:%M:%S') UTC"
echo "== Llamadas a chat/completions por código HTTP"
grep -o 'api.openai.com/v1/chat/completions "HTTP/1.1 [0-9]*' /tmp/openai_check_window.log \
  | awk '{print $NF}' | sort | uniq -c | sed 's/^/   /'
[ -s /tmp/openai_check_window.log ] || echo "   (ventana vacía)"

echo "== Llamadas por hora (UTC)"
grep 'api.openai.com/v1/chat/completions' /tmp/openai_check_window.log \
  | awk '{print substr($2,1,2) "h"}' | sort | uniq -c | sed 's/^/   /'

echo "== Errores de parámetros de OpenAI (400, unsupported, reasoning_effort, max_tokens)"
{ grep -n -E 'api\.openai\.com/.*"HTTP/1.1 [45][0-9][0-9]' /tmp/openai_check_window.log
  grep -n -i -E 'unsupported_(value|parameter)|BadRequestError|invalid_request_error|openai\.[A-Za-z]*Error' /tmp/openai_check_window.log
} | sort -t: -k1,1n -u | head -20 | sed 's/^/   /'
echo "   (fin; si no hay nada encima, ningún error de OpenAI)"

echo "== Tracebacks y errores en la ventana"
grep -c 'Traceback' /tmp/openai_check_window.log | sed 's/^/   tracebacks: /'
grep -n -E 'Traceback|^[A-Za-z]+Error:|ERROR' /tmp/openai_check_window.log | head -15 | sed 's/^/   /'

echo "== Resultados de los jobs con LLM"
grep -E 'Borradores generados: [1-9]|draft listo|Run terminado|propuestas nuevas|Materializ|preparad|caption|clips? propuest' \
  /tmp/openai_check_window.log | tail -15 | sed 's/^/   /'
REMOTE
