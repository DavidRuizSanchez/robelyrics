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

if [ ! -f "$TOKEN" ]; then
  echo "[gsc-weekly] sin token en $TOKEN; salgo"; exit 0
fi

cd "$REPO" || exit 0

echo "[gsc-weekly $(date -u +%F\ %H:%M)] fetch GSC (12 semanas)…"
PYTHONPATH="$REPO/api" arch -arm64 python3 -m scripts.seo.gsc_fetch_page_queries \
  --weeks 12 --out "$REPO/data/gsc_page_queries.json" || { echo "fetch falló"; exit 1; }

echo "[gsc-weekly] rsync del JSON a prod…"
rsync -az "$REPO/data/gsc_page_queries.json" "$REPO/data/gsc_queries.json" \
  robelyrics:/opt/robelyrics/data/ || { echo "rsync falló"; exit 1; }

echo "[gsc-weekly] informe de oportunidades en prod (email)…"
ssh robelyrics 'cd /opt/robelyrics && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T api python -m scripts.seo.gsc_optimize' \
  || echo "informe remoto falló (no crítico)"

echo "[gsc-weekly] hecho."
