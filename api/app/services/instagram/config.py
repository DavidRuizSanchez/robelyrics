"""Configuración del pipeline de Instagram.

Las credenciales se leen del entorno (cableadas al contenedor api en
docker-compose.yml). Si faltan, el pipeline degrada con elegancia: prepara
los posts pero no los publica.
"""
import os

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
