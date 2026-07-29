"""Configuración del pipeline de Instagram.

Las credenciales se leen del entorno (cableadas al contenedor api en
docker-compose.yml). Si faltan, el pipeline degrada con elegancia: prepara
los posts pero no los publica.
"""
import os
from datetime import date

# Robe falleció el 10 de diciembre de 2025. Caption e imagen abren con
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
# STEADY_INTERVAL_H horas. El cron dispara cada 15 min y este guard es quien
# decide de verdad: con disparos frecuentes, un post programado a las 19:40 sale
# a las 19:45 y no en el siguiente slot de 6 horas.
#
# El intervalo se subió de 5h a 15h en jul-2026. Con el cron antiguo (3 disparos
# al día) salían 21,5 posts/semana medidos, tres al día de contenido plantillero;
# el objetivo ahora son 10-12 semanales bien trabajados:
#     24 × 7 / 15 h ≈ 11,2 posts/semana
# OJO al tocarlo: como el cron dispara cada 15 min, este número es lo ÚNICO que
# limita el ritmo. Bajarlo a 5 devolvería casi 34 posts/semana.
BACKLOG_THRESHOLD = int(os.getenv("IG_BACKLOG_THRESHOLD", "4"))
BACKLOG_INTERVAL_H = int(os.getenv("IG_BACKLOG_INTERVAL_H", "10"))
STEADY_INTERVAL_H = int(os.getenv("IG_STEADY_INTERVAL_H", "15"))

# --- Reintentos de publicación --------------------------------------------
# Cuántas veces se reintenta un post que falló al publicar. Un fallo transitorio
# (Cloudinary, un timeout de Meta) dejaba el item en `failed` y ahí se moría: los
# dos selectores de la cola filtran por pending/prepared, así que nadie lo volvía
# a mirar. Se cuenta en `instagram_queue.attempts` y solo lo gastan los fallos
# atribuibles al item — si lo que está caído es la conexión con Meta, el post no
# tiene la culpa y no se le quema un intento.
MAX_PUBLISH_ATTEMPTS = int(os.getenv("IG_MAX_PUBLISH_ATTEMPTS", "3"))

# --- Aprobación ------------------------------------------------------------
# Todo el contenido nace `proposed` y NADIE lo publica sin que el admin lo
# apruebe en /biblioteca/admin/instagram. Antes solo pasaba por ahí el evergreen:
# las noticias entraban directas a `pending` y se publicaban sin que nadie las
# viera. Poniendo IG_AUTO_APPROVE=true se vuelve al automatismo anterior.
AUTO_APPROVE = os.getenv("IG_AUTO_APPROVE", "false").strip().lower() in (
    "1", "true", "yes", "si", "sí",
)


def estado_inicial() -> str:
    """Estado con el que nace un item recién encolado."""
    return "pending" if AUTO_APPROVE else "proposed"


# --- Formato ---------------------------------------------------------------
# Se intenta CARRUSEL siempre que el tema dé material verificado para ≥2
# diapositivas con sustancia; si no, se cae a foto única (que sigue siendo el
# camino por defecto y no ha cambiado). En el benchmark del nicho el carrusel de
# diseño fue el formato con más engagement con mucha diferencia.
# Poniendo IG_CAROUSEL=false solo se generan carruseles marcados a mano.
CAROUSEL_ENABLED = os.getenv("IG_CAROUSEL", "true").strip().lower() in (
    "1", "true", "yes", "si", "sí",
)
