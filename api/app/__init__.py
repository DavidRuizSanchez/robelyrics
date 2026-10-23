import logging

# httpx registra cada petición a nivel INFO con la URL COMPLETA, y los scripts de
# cron hacen `basicConfig(level=INFO)`: la YOUTUBE_API_KEY (`key=AIza…`) acababa en
# claro en /var/log/robelyrics-cron.log y en sus siete semanas de rotaciones
# (23-10-2026). Va aquí porque todo script de cron importa algo de `app`.
logging.getLogger("httpx").setLevel(logging.WARNING)
