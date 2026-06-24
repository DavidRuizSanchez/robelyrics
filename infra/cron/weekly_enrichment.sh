#!/usr/bin/env bash
# Enriquecimiento semanal del corpus de RobeLyrics.
#
# Encadena la ADQUISICIÓN y el DESTILADO de fan-content nuevo, que el bloque
# nocturno 03:30 (graph + embeddings) NO hace por sí solo. Se ejecuta antes de
# ese bloque (domingo 02:00 UTC desde production.crontab).
#
# Robustez: los fetch_* van con `|| true` — un foro o blog caído NO debe
# bloquear el destilado ni la reconstrucción del grafo. Los pasos de
# link/embed/distill van encadenados estrictos (`&&`): si uno falla de verdad,
# paramos y lo vemos en el log en vez de propagar basura.
#
# NO se incluyen fetch_reddit / fetch_press / fetch_genius_annotations /
# fetch_youtube: Reddit fuera por policy, prensa solo SEO, Genius roto por
# Cloudflare, y fetch_youtube fallaría desde la IP del datacenter (antibot).
# Los vídeos de YouTube entran por el Pipeline 2 (daemon local).
#
# Idempotente: todos los scripts son seguros de relanzar.
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/robelyrics}"
DC="${DC:-docker compose -f docker-compose.yml -f docker-compose.prod.yml}"

cd "$APP_DIR" || { echo "[✗] no se pudo cd a $APP_DIR"; exit 1; }

echo "===== weekly_enrichment $(date -u +'%Y-%m-%dT%H:%M:%SZ') ====="

# 1-2) Adquisición tolerante a fallos de fuente.
$DC exec -T api python -m scripts.research.fetch_forums || echo "[!] fetch_forums falló (se continúa)"
$DC exec -T api python -m scripts.research.fetch_blogs  || echo "[!] fetch_blogs falló (se continúa)"

# 3-9) Destilado + vectorización + grafo (estricto: si algo crítico falla, paramos).
$DC exec -T api python -m scripts.research.link_sources_to_songs \
  && $DC exec -T api python -m scripts.research.embed_interpretations \
  && $DC exec -T api python -m scripts.research.distill --only-missing \
  && $DC exec -T api python -m scripts.research.vectorize_consensus \
  && $DC exec -T api python -m scripts.research.update_interpretations_payload \
  && $DC exec -T api python -m scripts.research.embed_robe_voice \
  && $DC exec -T api python -m scripts.graph.build_graph
rc=$?

echo "===== weekly_enrichment fin (rc=$rc) ====="
exit "$rc"
