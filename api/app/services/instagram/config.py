"""Configuración del pipeline de Instagram.

Las credenciales se leen del entorno (cableadas al contenedor api en
docker-compose.yml). Si faltan, el pipeline degrada con elegancia: prepara
los posts pero no los publica.
"""
import os
from datetime import date

# Robe Iniesta falleció el 10 de diciembre de 2025. Caption e imagen abren con
# el contador memorial "Día X sin Robe".
ROBE_DEATH = date(2025, 12, 10)


def dias_sin_robe() -> int:
    return max(0, (date.today() - ROBE_DEATH).days)

# --- Meta / Instagram Graph API ---
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

# --- Cloudinary — hosting público de imágenes (la Graph API exige una URL) ---
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

SITE_URL = os.getenv("SITE_URL", "https://entreinteriores.com").rstrip("/")

# --- Parámetros de negocio ---
POSTS_PER_DAY = int(os.getenv("IG_POSTS_PER_DAY", "2"))
IMG_SIZE = (1080, 1080)               # formato cuadrado de Instagram
IMAGES_DIR = "/tmp/robelyrics_instagram"  # ficheros intermedios (efímeros)

# --- Frescura: la actualidad solo cubre la última semana ---
# Una noticia con artículo de más de N días no entra como tema (evita refritos
# de hechos viejos que un medio reedita con fecha reciente).
FRESHNESS_DAYS = int(os.getenv("IG_FRESHNESS_DAYS", "7"))

# --- Cadencia de publicación (cuentagotas) ---
# Mientras hay atasco (cola > BACKLOG_THRESHOLD) se publica cada
# BACKLOG_INTERVAL_H horas para drenarlo; en régimen normal, cada
# STEADY_INTERVAL_H horas. El cron dispara a 08,14,20 UTC (slots de 6h) y este
# guard decide. STEADY=5h (no 6) deja margen: con 6h exactos entre slots, un
# leve retraso del cron daría 5.99h < 6h y se saltaría una publicación.
BACKLOG_THRESHOLD = int(os.getenv("IG_BACKLOG_THRESHOLD", "4"))
BACKLOG_INTERVAL_H = int(os.getenv("IG_BACKLOG_INTERVAL_H", "4"))
STEADY_INTERVAL_H = int(os.getenv("IG_STEADY_INTERVAL_H", "5"))
