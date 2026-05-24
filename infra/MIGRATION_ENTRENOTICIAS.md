# Migración: jubilar Entre Noticias e integrar todo en entreinteriores.com

El proyecto local `goaltest/entrenoticias/` (Flask + launchd en el Mac) pasa
a vivir dentro de la api de RobeLyrics. Después de desplegar este cambio,
hay que apagar Entre Noticias y volar el `host.docker.internal` que ya no
hace falta.

## 1. Variables de entorno en prod

Añadir a `/opt/robelyrics/.env` del server las credenciales del pipeline de
Instagram (mismas que en `goaltest/entrenoticias/.env`):

```
META_APP_ID=...
META_APP_SECRET=...
INSTAGRAM_ACCOUNT_ID=...
INSTAGRAM_ACCESS_TOKEN=...        # token de larga duración, renovar ~julio 2026
IG_POSTS_PER_DAY=2

CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

## 2. Desplegar el código

```bash
# desde el repo local
rsync -avz --exclude='.env' --exclude='node_modules' --exclude='.git' \
  ./ robelyrics:/opt/robelyrics/

ssh robelyrics
cd /opt/robelyrics
docker compose -f docker-compose.yml -f docker-compose.prod.yml build api
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api
docker compose exec -T api alembic upgrade head    # crea news_items + instagram_queue
```

## 3. Instalar el cron actualizado

```bash
ssh robelyrics
crontab -l > /tmp/crontab.bak
crontab -e
# pegar el contenido de infra/cron/production.crontab
```

Las nuevas líneas (resumen):

```
30 7 * * *  aggregate         # 07:30 — agrega 27 fuentes a news_items
30 8 * * *  prepare_daily     # 08:30 — selecciona temas IG y prepara
30 12 * * * publish_next      # 12:30 — publica el siguiente
30 20 * * * publish_next      # 20:30 — publica el siguiente
```

## 4. Apagar Entre Noticias en el Mac

```bash
# Parar las tareas launchd
launchctl unload ~/Library/LaunchAgents/com.entrenoticias.*.plist
ls ~/Library/LaunchAgents/com.entrenoticias.*.plist   # comprobar
# Opcional: borrar los plist
rm ~/Library/LaunchAgents/com.entrenoticias.*.plist

# Parar el Flask de :8770 si está corriendo
pkill -f 'python.*entrenoticias/app.py'

# Archivar (recomendado, NO borrar — guarda el .env con el token IG):
mv "/Users/david.ruiz/Documents/Claude Code/goaltest/entrenoticias" \
   "/Users/david.ruiz/Documents/Claude Code/goaltest/entrenoticias.archived"
```

## 5. Comprobaciones post-deploy

```bash
# En el server, verificar que el agregador escribe
docker compose exec -T api python -m scripts.news.aggregate --dry-run

# Pre-vuelo del pipeline IG (sin publicar)
docker compose exec -T api python -m scripts.instagram.prepare_daily

# Panel admin
open https://entreinteriores.com/biblioteca/admin/instagram
# El badge de cuenta debe decir: ✓ entreinterioresrobe
```

## Qué desaparece y qué llega

- ❌ `data/news_whitelist.yaml`        → reemplazado por `data/news_sources.yaml`
- ❌ `host.docker.internal:8770`       → ya no hay agregador remoto que consumir
- ❌ Proyecto local `entrenoticias/`   → todo dentro de la api de RobeLyrics
- ❌ launchd del Mac                   → cron de Hetzner
- ✅ Una sola base de código, un solo `.env`, un solo dedup, una sola cola.
- ✅ Panel admin web en /biblioteca/admin/instagram para gestionar la cola.
- ✅ Reddit entra a la ecuación como `ig-only` (RSS público oficial, sin evasión).
