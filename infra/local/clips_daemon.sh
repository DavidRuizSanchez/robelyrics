#!/usr/bin/env bash
# Daemon local (Mac, IP residencial) que descarga los clips de YouTube pedidos
# desde el panel para publicarlos en Instagram.
#
# Hermano de `juancares_daemon.sh` y por el MISMO motivo: yt-dlp desde la IP del
# servidor recibe un bloqueo de YouTube. Aquí la descarga sale por la red de
# casa. Sin evasión de ningún tipo: se usa la red donde sí se puede.
#
# Lo dispara launchd cada ~10 min (ver com.robelyrics.clips.plist). Ejecuta el
# procesador DENTRO del contenedor api LOCAL, que habla con prod por HTTP:
# reclama el clip, lo baja recortado, le quema la atribución del canal, lo sube
# a Cloudinary y devuelve la URL a producción.
#
# Lock con mkdir (atómico y PORTABLE: macOS no trae flock).
set -uo pipefail

CONTAINER="${ROBELYRICS_CONTAINER:-robelyrics-api}"
LOCKDIR="/tmp/robelyrics_clips_daemon.lock"

# Lock añejo (>2 h, de una pasada que murió sin limpiar) → lo retiramos.
if [ -d "$LOCKDIR" ] && [ -n "$(find "$LOCKDIR" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
  rmdir "$LOCKDIR" 2>/dev/null || true
fi
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "[$(date -u +%H:%M:%S)] otra pasada en curso, salgo"
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM

# Si el contenedor no está vivo, salimos en silencio: la Mac estará dormida.
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[$(date -u +%H:%M:%S)] contenedor $CONTAINER no está corriendo, salgo"
  exit 0
fi

echo "===== clips_daemon $(date -u +'%Y-%m-%dT%H:%M:%SZ') ====="
docker exec "$CONTAINER" python -m scripts.instagram.process_clips
echo "===== fin (rc=$?) ====="
