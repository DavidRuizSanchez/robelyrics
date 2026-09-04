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
# El intervalo se subió de 5h a 15h en jul-2026 para bajar de 21,5 a ~11 posts
# semanales... y NO bajó: medido el 04-09-2026, las siete semanas siguientes
# dieron 17, 20, 20, 20, 21, 21 y 21 posts. El cambio no sirvió de nada porque
# quien mandaba no era STEADY sino BACKLOG:
#
#   con el umbral en 4, la cola (que se movía entre 5 y 13) estaba SIEMPRE por
#   encima, así que el modo atasco era el estado permanente y el intervalo de
#   15 h no se aplicaba casi nunca. 24/10 = 2,4 posts al día = 16,8 a la semana,
#   más lo que sale por `due_pinned` al margen del cuentagotas ≈ 20.
#
# Arreglado subiendo el umbral para que el atasco vuelva a ser excepcional (la
# cola normal cabe por debajo) y ajustando el régimen a 12 h:
#     24 × 7 / 12 h = 14 posts/semana, más los fijados ≈ 15.
#
# OJO al tocarlo: como el cron dispara cada 15 min, estos números son lo ÚNICO
# que limita el ritmo. Y no basta con mirar STEADY: si la cola supera el umbral,
# el que manda es BACKLOG. Para saber a qué ritmo se publica DE VERDAD hay que
# contar los publicados por semana, no leer esta constante.
BACKLOG_THRESHOLD = int(os.getenv("IG_BACKLOG_THRESHOLD", "15"))
BACKLOG_INTERVAL_H = int(os.getenv("IG_BACKLOG_INTERVAL_H", "10"))
STEADY_INTERVAL_H = int(os.getenv("IG_STEADY_INTERVAL_H", "12"))

# --- Reintentos de publicación --------------------------------------------
# Cuántas veces se reintenta un post que falló al publicar. Un fallo transitorio
# (Cloudinary, un timeout de Meta) dejaba el item en `failed` y ahí se moría: los
# dos selectores de la cola filtran por pending/prepared, así que nadie lo volvía
# a mirar. Se cuenta en `instagram_queue.attempts` y solo lo gastan los fallos
# atribuibles al item — si lo que está caído es la conexión con Meta, el post no
# tiene la culpa y no se le quema un intento.
MAX_PUBLISH_ATTEMPTS = int(os.getenv("IG_MAX_PUBLISH_ATTEMPTS", "3"))

# Cuánto espera un post que falló antes de volver a intentarlo. Sin esto, el
# cron (cada 15 min) quemaba los 3 intentos en 45 minutos: en agosto de 2026 la
# cuenta se restringió y 47 posts quedaron condenados en día y medio, mucho
# antes de que ningún humano pudiera enterarse. Con 6 h, tres intentos ocupan
# medio día y la alerta llega primero.
RETRY_COOLDOWN_H = int(os.getenv("IG_RETRY_COOLDOWN_H", "6"))

# --- Cortacircuitos de publicación -----------------------------------------
# Cuando Meta nos bloquea (cuenta restringida, token muerto, cuota agotada) no
# tiene sentido seguir subiendo imágenes a Cloudinary y creando containers cada
# 15 minutos. El estado NO se guarda en ningún flag: se deduce de los fallos
# recientes de la propia cola, así se apaga solo y nadie tiene que acordarse de
# cerrarlo. BLOCK_WINDOW_H es cuánto dura el corte antes de volver a sondear.
BLOCK_WINDOW_H = int(os.getenv("IG_BLOCK_WINDOW_H", "6"))

# Cuántos items DISTINTOS tienen que fallar seguidos para dar por hecho que la
# caída es global aunque no reconozcamos el código. Es la red que hace asumible
# que un código desconocido gaste intento (ver `errors.quema_intento`).
GLOBAL_STREAK = int(os.getenv("IG_GLOBAL_STREAK", "3"))

# --- Alerta de salud --------------------------------------------------------
# Horas sin publicar TENIENDO material antes de avisar por correo. Con
# STEADY_INTERVAL_H = 15 h, 48 h son tres turnos perdidos: ya no es casualidad.
# Este es el detector que no depende de clasificar nada — cubre el cron muerto,
# docker caído, Cloudinary y cualquier bug nuestro futuro.
ALERT_STALE_H = int(os.getenv("IG_ALERT_STALE_H", "48"))

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
