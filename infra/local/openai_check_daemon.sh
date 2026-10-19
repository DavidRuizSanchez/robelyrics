#!/bin/bash
# Vigilancia programada de la migración a gpt-6-luna (deploy 19-10-2026 09:57:45 UTC).
# La lanza launchd (com.robelyrics.openai-check) cada día a las 10:47 del 20 al
# 26-oct y una última vez el 26-oct a las 12:13. No necesita una sesión de Claude
# abierta: ejecuta check_openai_migration.sh, guarda el informe, decide el veredicto
# y avisa con terminal-notifier. Solo lectura sobre prod. Tras la última pasada se
# desactiva solo.
#
# Instalar: ver la cabecera de com.robelyrics.openai-check.plist.
set -u

BASE="/Users/david.ruiz/Library/Application Support/robelyrics"
CHECK="${OPENAI_CHECK_SCRIPT:-$BASE/check_openai_migration.sh}"  # sobrescribible solo para tests
REPORTS="$BASE/openai-check"
LABEL="com.robelyrics.openai-check"
PLIST="/Users/david.ruiz/Library/LaunchAgents/$LABEL.plist"
DEPLOY_UTC="2026-10-19 09:57:45"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "$REPORTS"

today=$(TZ=Europe/Madrid date +%Y-%m-%d)
hour=$(TZ=Europe/Madrid date +%H)
test_mode=0; [ "${1:-}" = "--test" ] && test_mode=1
# Guarda de fechas: launchd en macOS Tahoe puede disparar de más.
if [ $test_mode -eq 0 ] && [[ "$today" < "2026-10-20" || "$today" > "2026-10-26" ]]; then exit 0; fi

is_final=0
if [[ "$today" == "2026-10-26" && "$hour" -ge 12 ]]; then is_final=1; fi
slot="$today-$([ $is_final -eq 1 ] && echo final || echo diaria)"
[ $test_mode -eq 1 ] && { slot="$today-test"; is_final=0; }
[ $test_mode -eq 0 ] && [ -f "$REPORTS/$slot.done" ] && exit 0

if [ $is_final -eq 1 ]; then
  since="$DEPLOY_UTC"
else
  since=$(date -u -v-26H '+%Y-%m-%d %H:%M:%S')
  [[ "$since" < "$DEPLOY_UTC" ]] && since="$DEPLOY_UTC"
fi

report="$REPORTS/$slot.txt"
bash "$CHECK" "$since" > "$report" 2>&1
check_exit=$?

calls=$(awk '/^== Llamadas a chat/{f=1;next} /^==/{f=0} f' "$report" | awk '{s+=$1} END{print s+0}')
openai_errors=$(awk '/^== Errores de parámetros/{f=1;next} /\(fin;/{f=0} f' "$report" | grep -c .)
tracebacks=$(grep -o 'tracebacks: [0-9]*' "$report" | awk '{print $2}')
non200=$(awk '/^== Llamadas a chat/{f=1;next} /^==/{f=0} f && $2 != "200"' "$report" | awk '{s+=$1} END{print s+0}')

if [ $check_exit -ne 0 ] || ! grep -q '^== Ventana' "$report"; then
  verdict="ERROR"; message="No se pudo leer el log de prod (ssh robelyrics). Mira $report"
elif [ "$openai_errors" -gt 0 ] || [ "$non200" -gt 0 ]; then
  verdict="ALERTA"; message="$openai_errors errores de OpenAI y $non200 llamadas no-200 de $calls. Valorar la vuelta atrás a gpt-4o."
elif [ "${tracebacks:-0}" -gt 0 ]; then
  verdict="AVISO"; message="$calls llamadas OK, 0 errores de OpenAI, pero $tracebacks tracebacks en el log: revisar."
else
  verdict="OK"
  if [ "$calls" -eq 0 ]; then message="0 llamadas al modelo en la ventana (los crons no tuvieron trabajo). Sin errores ni tracebacks."
  else message="$calls llamadas a gpt-6-luna, todas 200. Sin errores ni tracebacks."; fi
fi

{ echo; echo "== VEREDICTO: $verdict — $message"; echo "== Generado: $(date '+%Y-%m-%d %H:%M:%S %Z')"; } >> "$report"
echo "$(date '+%Y-%m-%d %H:%M:%S') $slot $verdict calls=$calls openai_errors=$openai_errors non200=$non200 tracebacks=${tracebacks:-?}" >> "$REPORTS/history.log"
touch "$REPORTS/$slot.done"

sound=$([ "$verdict" = "OK" ] && echo "default" || echo "Basso")
/usr/local/bin/terminal-notifier -group "robelyrics.openai-check" -sound "$sound" \
  -title "RobeLyrics · gpt-6-luna: $verdict" -message "$message" -open "file://${report// /%20}" >/dev/null 2>&1

if [ $is_final -eq 1 ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') última pasada hecha: se desactiva el agente" >> "$REPORTS/history.log"
  mv "$PLIST" "$PLIST.disabled" 2>/dev/null
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
fi
exit 0
