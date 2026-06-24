# Daemon local de ingesta de YouTube (Juancares + entrevistas de Robe)

Pieza local del pipeline **"1 click → autónomo"**. Vive en la **Mac del user**
(no en el servidor) porque la descarga/transcripción de YouTube debe salir por
una **IP residencial**: desde la IP del datacenter de Hetzner salta el antibot.
Sin herramientas de evasión — usamos la red donde sí se puede.

## Cómo encaja en el pipeline

1. **Server** (cron cada 3 días): `scripts.youtube.detect_uploads` detecta
   uploads nuevos de `@juancaraes` + siembra entrevistas de `data/robe_interviews.yaml`,
   los encola (`detected`) y manda al admin un **email con un CTA firmado**.
2. **Admin** (1 click): el enlace `/api/public/youtube-ingest?token=…` marca el
   batch como `approved`.
3. **Esta Mac** (launchd, cada 15 min): el daemon hace polling de los `approved`,
   transcribe en local (yt-dlp → ffmpeg → Whisper) y **empuja la transcripción a
   prod** por HTTP (`/ingest/youtube/{id}/complete`), que la guarda como
   `InterpretationSource`. El embed lo hace el Pipeline 1 semanal del server.

## Requisitos

- Docker Desktop corriendo con el contenedor **`robelyrics-api`** levantado en
  local (`docker compose up -d`). El contenedor ya trae `yt-dlp`, `ffmpeg` y el
  cliente OpenAI.
- En el `.env` del contenedor local:
  - `PROD_API_URL` → base de la API de prod (p.ej. `https://entreinteriores.com/api`).
  - `INGEST_API_KEY` → **el mismo** valor que en el `.env` de prod.
  - `OPENAI_API_KEY` → para Whisper.

## Instalación del agent launchd

⚠️ **El wrapper NO puede vivir en `~/Documents` / `~/Desktop` / `~/Downloads`**:
macOS (TCC) le niega a launchd ejecutar ahí (`Operation not permitted`). Por eso
se copia a `~/Library/Application Support/robelyrics/`.

```bash
# 1. Copia el wrapper a una ruta no protegida por TCC
mkdir -p "$HOME/Library/Application Support/robelyrics"
cp infra/local/juancares_daemon.sh "$HOME/Library/Application Support/robelyrics/"
chmod +x "$HOME/Library/Application Support/robelyrics/juancares_daemon.sh"

# 2. Copia el plist. Si tu home no es /Users/david.ruiz, edita la ruta absoluta
#    de ProgramArguments (launchd no expande ~ ni $HOME).
cp infra/local/com.robelyrics.juancares.plist ~/Library/LaunchAgents/

# 3. Cárgalo (RunAtLoad hace una primera pasada inmediata)
launchctl load ~/Library/LaunchAgents/com.robelyrics.juancares.plist

# Estado / logs
launchctl list | grep robelyrics
tail -f /tmp/robelyrics_juancares_daemon.log

# Recargar tras editar el plist
launchctl unload ~/Library/LaunchAgents/com.robelyrics.juancares.plist
launchctl load   ~/Library/LaunchAgents/com.robelyrics.juancares.plist
```

## Probar a mano (sin esperar a launchd)

```bash
bash infra/local/juancares_daemon.sh
# o directo dentro del contenedor:
docker exec robelyrics-api python -m scripts.youtube.process_queue --max 1
```

## Notas

- **Lock (mkdir)**: si una pasada tarda más de 15 min, la siguiente se salta (no
  se solapan). Concurrencia 1 a propósito (`docker exec` se estanca bajo carga).
  Se usa `mkdir` y no `flock` porque macOS no trae `flock`.
- Si la Mac está dormida o Docker apagado, el daemon **sale en silencio** (no es
  error): retoma en la siguiente pasada.
- Un vídeo que falla queda `failed` con el error y **se reintenta solo** en las
  siguientes pasadas hasta 3 intentos (el endpoint `pending` devuelve los
  `failed` con `attempts < 3`). Pasado ese tope, se queda `failed` y se mira a
  mano en `youtube_ingest_queue`.
