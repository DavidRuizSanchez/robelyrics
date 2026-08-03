#!/bin/sh
# Pipeline completo del keyword research, de la ola cruda al entregable.
#
#   docker compose exec api sh scripts/seo/kw_pipeline.sh <run_id>
#
# Cada paso es idempotente y reanudable: la caché de respuestas crudas vive en
# kw_out/_raw/ y se comparte entre runs, así que relanzar no vuelve a pagar.
set -e
RUN="${1:?uso: kw_pipeline.sh <run_id>}"

echo "== 1/4 fusión DataForSEO + Ahrefs + clustering semántico =="
python -m scripts.seo.kw_merge --run "$RUN"

echo "== 2/4 atribución: cada keyword a un solo dueño =="
python -m scripts.seo.kw_attribute --run "$RUN"

echo "== 3/4 visor HTML =="
python -m scripts.seo.kw_artifact --run "$RUN"

echo "== 4/4 trazabilidad (SOURCES.md + costs.csv) =="
python -m scripts.seo.kw_sources --run "$RUN"

echo
echo "Entregable en kw_out/$RUN/"
echo "  atribuido/master.csv     universo con cada keyword atribuida"
echo "  atribuido/by-owner/*.csv un CSV por disco y por canción"
echo "  atribuido/artifact.html  visor navegable"
echo "  entregable/clusters.csv  clusters semánticos"
echo "  entregable/discrepancias.csv  divergencias >2x entre herramientas"
echo "  revisar_homonimos.csv    casan por título sin marca (ojo humano)"
echo "  offtopic.csv             descartado por la guarda, guardado para auditar"
echo "  SOURCES.md + costs.csv   trazabilidad y coste medido"
