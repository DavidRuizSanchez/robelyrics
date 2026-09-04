"""video_clips: clips de YouTube para Instagram, con su procedencia

El usuario decidió publicar clips de cualquier canal interesante sin pedir
permiso previo, gestionando las reclamaciones si llegan. Esta tabla es lo que
hace esa decisión sostenible: por cada clip queda registrado DE DÓNDE salió, qué
tramo se usó, quién lo aprobó y en qué publicación acabó. Si llega un aviso, se
responde en minutos y se retira con un botón — igual que `image_guard` con las
fotos.

El ciclo es el mismo de `youtube_ingest_queue` y por el mismo motivo: la IP del
servidor está bloqueada por YouTube, así que descarga un daemon en la Mac
(`infra/local/`) y empuja el resultado por HTTP.

Revision ID: igclip2026_01
Revises: igmix2026_01
"""
from alembic import op
import sqlalchemy as sa

revision = "igclip2026_01"
down_revision = "igmix2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_clips",
        sa.Column("id", sa.Integer, primary_key=True),
        # --- Procedencia (lo que permite responder a una reclamación) ---
        sa.Column("video_id", sa.String(32), nullable=False, index=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("video_title", sa.String(500)),
        sa.Column("channel_title", sa.String(200)),
        sa.Column("channel_url", sa.String(500)),
        # --- Tramo utilizado ---
        sa.Column("start_s", sa.Float, nullable=False, server_default="0"),
        sa.Column("end_s", sa.Float, nullable=False),
        sa.Column("subtitle", sa.Text),          # texto sobreimpreso, opcional
        # --- Ciclo de vida ---
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="requested", index=True),
        sa.Column("local_path", sa.String(500)),
        sa.Column("url_cdn", sa.String(700)),
        sa.Column("cloudinary_public_id", sa.String(200)),
        sa.Column("duration_s", sa.Float),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
        # --- Trazabilidad ---
        sa.Column("requested_by", sa.String(200)),
        sa.Column("queue_item_id", sa.Integer,
                  sa.ForeignKey("instagram_queue.id", ondelete="SET NULL")),
        sa.Column("ig_media_id", sa.String(64)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("retired_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('requested','downloading','ready','published',"
            "'retired','failed')",
            name="ck_video_clips_status",
        ),
        sa.CheckConstraint("end_s > start_s", name="ck_video_clips_tramo"),
    )
    # Los índices de `video_id` y `status` ya los crea `index=True` en sus
    # columnas: añadirlos otra vez aquí reventaba con DuplicateTable.


def downgrade() -> None:
    op.drop_table("video_clips")
