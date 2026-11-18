#!/usr/bin/env bash
# Seguimiento a 1, 2, 3 y 4 semanas de los headings humanizados (11-11-2026).
#
# Corre en la Mac porque el token de GSC vive aquí (como gsc_weekly.sh). Cadena:
#   prod: qué páginas se cambiaron y cuándo (content_revisions)
#   mac:  GSC page+date, page+query+date e inspección de URL
#   prod: si GSC ya cubre una semana sin mandar, informe a ADMIN_EMAIL
# Datos, estado (enviadas.txt) e informes de cada semana: en $DIR.
# launchd lo lanza cada día; el informe solo sale cuando toca, así que da igual
# que la Mac pase días dormida. Con la semana 4 mandada se desinstala solo.
set -uo pipefail

REPO="${ROBELYRICS_REPO:-$HOME/Documents/Claude Code/RobeLyrics}"
# Los datos van FUERA de ~/Documents: lanzado por launchd, macOS (TCC) no deja a
# rsync leer ahí («Operation not permitted»). Es lo que tenía parado gsc_weekly.sh.
DIR="$HOME/Library/Application Support/robelyrics/seguimiento_headings"
PLIST="$HOME/Library/LaunchAgents/com.robelyrics.seguimiento-headings.plist"
DC='docker compose -f docker-compose.yml -f docker-compose.prod.yml'
LOCKDIR="/tmp/robelyrics_seguimiento_headings.lock"

if ! mkdir "$LOCKDIR" 2>/dev/null; then
  if [ -n "$(find "$LOCKDIR" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
    rmdir "$LOCKDIR"; mkdir "$LOCKDIR"
  else
    echo "otra pasada en curso"; exit 0
  fi
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM

avisar() {
  echo "[seguimiento-headings] AVISO: $1"
  osascript -e "display notification \"$1\" with title \"RobeLyrics · headings\" sound name \"Basso\"" \
    >/dev/null 2>&1 || true
}

mkdir -p "$DIR"
cd "$REPO" || exit 1
echo "[seguimiento-headings $(date -u +%F\ %H:%M)] inicio"

# El estado vive aquí: en prod `data/` va en solo lectura dentro del contenedor.
ESTADO="$DIR/enviadas.txt"   # una semana por línea
touch "$ESTADO"
if grep -qx 4 "$ESTADO"; then
  echo "semana 4 ya enviada: me desinstalo"
  launchctl unload "$PLIST" 2>/dev/null; rm -f "$PLIST"; exit 0
fi
ENVIADAS=$(paste -sd, "$ESTADO")

ssh robelyrics "cd /opt/robelyrics && $DC exec -T api python -m scripts.seo.seguimiento_headings exportar" \
  > "$DIR/cambios.json.tmp" && mv "$DIR/cambios.json.tmp" "$DIR/cambios.json" \
  || { avisar "No se pudo leer de prod qué páginas se cambiaron"; exit 1; }

# Seguimiento conjunto (11-11-2026): las páginas a las que se cambia el title por
# tandas se apartan del informe de headings desde ese día.
ssh robelyrics "cd /opt/robelyrics && $DC exec -T api python -m scripts.seo.seguimiento_headings exportar --titles" \
  > "$DIR/titles.json.tmp" && mv "$DIR/titles.json.tmp" "$DIR/titles.json" \
  || { avisar "No se pudo leer de prod qué titles se cambiaron"; exit 1; }

PYTHONPATH="$REPO/api" arch -arm64 python3 -m scripts.seo.seguimiento_headings descargar \
  --cambios "$DIR/cambios.json" --out "$DIR/gsc.json" \
  || { avisar "Falló la descarga de GSC. Si es invalid_grant: python -m scripts.seo.gsc_reauth"; exit 1; }

rsync -az "$DIR/cambios.json" "$DIR/titles.json" "$DIR/gsc.json" robelyrics:/opt/robelyrics/data/seguimiento_headings/ \
  || { avisar "rsync a prod falló"; exit 1; }

SALIDA=$(ssh robelyrics "cd /opt/robelyrics && $DC exec -T api python -m scripts.seo.seguimiento_headings informe --enviadas '$ENVIADAS'") \
  || { avisar "El informe de seguimiento de headings falló en prod"; exit 1; }
K=$(printf '%s\n' "$SALIDA" | sed -n 's/^SEMANA \([1-4]\)$/\1/p' | head -1)
if [ -n "$K" ]; then
  echo "$K" >> "$ESTADO"
  # Copia local del informe y de los CSV (mismos datos que el correo).
  PYTHONPATH="$REPO/api" arch -arm64 python3 -m scripts.seo.seguimiento_headings informe \
    --semana "$K" --no-email --guardar --dir "$DIR" > /dev/null \
    || avisar "Semana $K enviada, pero no se pudo guardar la copia local"
  echo "semana $K enviada"
else
  echo "nada que mandar todavía"
fi
echo "[seguimiento-headings] hecho"
