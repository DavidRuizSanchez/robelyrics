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

---

## Daemon de CLIPS de vídeo para Instagram

Hermano del de Juancares y por el mismo motivo: yt-dlp desde la IP del servidor
recibe un bloqueo de YouTube, así que los clips se bajan desde casa.

**Qué hace**: cada 10 minutos pregunta a producción si hay clips pedidos desde
el panel; por cada uno, baja SOLO el tramo indicado, lo pasa a 9:16, le quema
encima la atribución del canal, lo sube a Cloudinary y devuelve la URL.

### Instalación (una vez)

```bash
# 1. Copiar el wrapper fuera de ~/Documents (TCC bloquea a launchd ahí)
mkdir -p ~/Library/Application\ Support/robelyrics
cp infra/local/clips_daemon.sh ~/Library/Application\ Support/robelyrics/
chmod +x ~/Library/Application\ Support/robelyrics/clips_daemon.sh

# 2. Instalar el agente de launchd
cp infra/local/com.robelyrics.clips.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.robelyrics.clips.plist

# 3. Comprobar
launchctl list | grep robelyrics
tail -f /tmp/robelyrics_clips_daemon.log
```

El contenedor `robelyrics-api` local necesita en su `.env`:
`INGEST_API_KEY` (el mismo de producción), `PROD_API_URL` y las credenciales de
Cloudinary.

### Probar a mano, sin esperar al temporizador

```bash
docker exec robelyrics-api python -m scripts.instagram.process_clips --dry-run
docker exec robelyrics-api python -m scripts.instagram.process_clips
```

### Si algo va mal

Un clip que falla se reintenta hasta 3 veces y luego queda en `failed` con el
motivo en la columna `error` de `video_clips`. El daemon sale en silencio si
Docker está apagado o la Mac dormida: no es un error.
