#!/usr/bin/env bash
# Job SEMANAL local (Mac) de F2.5: auto-optimización SEO con datos GSC.
#
# Corre AQUÍ (no en el server) porque el token OAuth de GSC de
# davidruizsanchez@gmail.com da acceso a varias propiedades personales/cliente
# (bbva, advicomasesores, segurosysalud, davidruizsanchez.es, entreinteriores.com)
# y no queremos ese token en el server de prod. El token vive solo en la Mac
# (~/.config/entreinteriores/gsc-token.json), se refresca solo.
#
# Cadena: fetch (token local) → rsync del JSON a prod → dispara el INFORME de
# oportunidades en prod (email al admin). Nada se auto-publica: el email lista las
# URLs a mejorar; David decide (o corre gsc_optimize --apply a mano).
#
# Lo dispara launchd (com.entreinteriores.gsc-weekly.plist), lunes por la mañana.
# Lock con mkdir (portátil; macOS no trae flock).
set -uo pipefail

REPO="${ROBELYRICS_REPO:-$HOME/Documents/Claude Code/RobeLyrics}"
LOCKDIR="/tmp/entreinteriores_gsc_weekly.lock"
TOKEN="$HOME/.config/entreinteriores/gsc-token.json"

if [ -d "$LOCKDIR" ] && [ -n "$(find "$LOCKDIR" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
  rmdir "$LOCKDIR" 2>/dev/null || true
fi
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "[$(date -u +%H:%M)] otra pasada en curso, salgo"; exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM

# Un fallo aquí se quedaba en /tmp/entreinteriores-gsc-weekly.log, que no lee
# nadie: el job moría en silencio y los datos de GSC se quedaban congelados sin
# que se notara. Como esto corre en la Mac, el aviso va al centro de
# notificaciones, que es donde sí se ve.
avisar() {
  echo "[gsc-weekly] AVISO: $1"
  osascript -e "display notification \"$1\" with title \"RobeLyrics · GSC\" sound name \"Basso\"" \
    >/dev/null 2>&1 || true
}

if [ ! -f "$TOKEN" ]; then
  avisar "No hay token en $TOKEN. Recréalo: python -m scripts.seo.gsc_reauth"
  exit 1
fi

cd "$REPO" || exit 0

echo "[gsc-weekly $(date -u +%F\ %H:%M)] fetch GSC (12 semanas)…"
if ! PYTHONPATH="$REPO/api" arch -arm64 python3 -m scripts.seo.gsc_fetch_page_queries \
     --weeks 12 --out "$REPO/data/gsc_page_queries.json"; then
  # Causa casi segura: `invalid_grant`. El token caduca a los SIETE DÍAS mientras
  # la app OAuth siga en modo *Testing* en Cloud Console. Publicarla quita el
  # límite y esto deja de pasar; renovar a mano solo compra otra semana.
  avisar "El fetch de GSC falló (token caducado?). Arréglalo con: python -m scripts.seo.gsc_reauth · Definitivo: publica la app OAuth en Cloud Console y deja de caducar cada 7 días."
  exit 1
fi

echo "[gsc-weekly] rsync del JSON a prod…"
rsync -az "$REPO/data/gsc_page_queries.json" "$REPO/data/gsc_queries.json" \
  robelyrics:/opt/robelyrics/data/ || { echo "rsync falló"; exit 1; }

echo "[gsc-weekly] informe de oportunidades en prod (email)…"
ssh robelyrics 'cd /opt/robelyrics && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T api python -m scripts.seo.gsc_optimize' \
  || echo "informe remoto falló (no crítico)"

echo "[gsc-weekly] hecho."
