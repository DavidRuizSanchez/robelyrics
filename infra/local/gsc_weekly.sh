#!/usr/bin/env bash
# Job SEMANAL local (Mac) de F2.5: auto-optimización SEO con datos GSC.
#
# Corre AQUÍ (no en el server) porque el token OAuth de GSC de
# davidruizsanchez@gmail.com da acceso a varias propiedades personales/cliente
# (bbva, advicomasesores, segurosysalud, davidruizsanchez.es, entreinteriores.com)
# y no queremos ese token en el server de prod. El token vive solo en la Mac
# (~/.config/entreinteriores/gsc-token.json), se refresca solo.
#
# Cadena: fetch (token local) → rsync del JSON a prod → DETECCIÓN de oportunidades
# en prod, que encola lo accionable y manda el correo con los botones. Nada se
# auto-publica: el primer clic solo PREPARA un borrador y llega un segundo correo
# con el antes/después antes de que nada toque el sitio.
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
  # Hasta el 17-09-2026 la causa era siempre `invalid_grant`: con la app OAuth en
  # modo *Prueba* el token caducaba a los 7 días. Ya está publicada y no caduca
  # por tiempo, así que un `invalid_grant` ahora es una revocación (cambio de
  # contraseña, permisos retirados, 6 meses sin uso) o que la app volvió a Prueba.
  avisar "El fetch de GSC falló. Si es invalid_grant: python -m scripts.seo.gsc_reauth (con davidruizsanchez@gmail.com). Si el reauth avisa de que el token caduca, la app OAuth ha vuelto a modo Prueba."
  exit 1
fi

echo "[gsc-weekly] rsync del JSON a prod…"
rsync -az "$REPO/data/gsc_page_queries.json" "$REPO/data/gsc_queries.json" \
  robelyrics:/opt/robelyrics/data/ || { echo "rsync falló"; exit 1; }

echo "[gsc-weekly] detección de oportunidades en prod (email con botones)…"
ssh robelyrics 'cd /opt/robelyrics && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T api python -m scripts.seo.seo_queue --detect' \
  || avisar "La detección de oportunidades SEO falló en prod. El volcado de GSC sí se subió."

echo "[gsc-weekly] hecho."
