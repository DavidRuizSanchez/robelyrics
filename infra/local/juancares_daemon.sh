#!/usr/bin/env bash
# Daemon local (Mac, IP residencial) del pipeline de ingesta de YouTube.
#
# Lo dispara launchd cada ~15 min (ver com.robelyrics.juancares.plist). Ejecuta
# el procesador de cola DENTRO del contenedor api LOCAL, que habla SOLO con prod
# por HTTP: descarga/transcribe lo aprobado y lo empuja a producción.
#
# La descarga sale por la IP de casa (residencial) → esquiva el antibot de
# YouTube que bloquea la IP del datacenter del servidor. Sin evasión: usamos la
# red donde sí se puede.
#
# Lock con mkdir (atómico y PORTABLE: macOS no trae flock, que es de Linux).
# Evita solapamientos si una pasada tarda más que el intervalo. Concurrencia 1
# a propósito (gotcha: docker exec se estanca bajo carga).
set -uo pipefail

CONTAINER="${ROBELYRICS_CONTAINER:-robelyrics-api}"
LOCKDIR="/tmp/robelyrics_juancares_daemon.lock"

# Lock añejo (>2 h, de una pasada que murió sin limpiar) → lo retiramos.
if [ -d "$LOCKDIR" ] && [ -n "$(find "$LOCKDIR" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
  rmdir "$LOCKDIR" 2>/dev/null || true
fi
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "[$(date -u +%H:%M:%S)] otra pasada en curso, salgo"
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM

# ¿Está vivo el contenedor? Si no, salimos en silencio (la Mac estará dormida o
# docker apagado): no es un error, simplemente no toca trabajar ahora.
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[$(date -u +%H:%M:%S)] contenedor $CONTAINER no está corriendo, salgo"
  exit 0
fi

echo "===== juancares_daemon $(date -u +'%Y-%m-%dT%H:%M:%SZ') ====="
docker exec "$CONTAINER" python -m scripts.youtube.process_queue
echo "===== fin (rc=$?) ====="
