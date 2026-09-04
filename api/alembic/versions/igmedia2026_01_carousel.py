"""instagram_queue: soporte de carrusel (varias imágenes por post)

Hasta ahora un item tenía UNA imagen (`image_path` + `image_url`, singulares).
Para publicar carruseles hace falta una colección ordenada, y como el panel va a
poder reordenar y regenerar diapositivas sueltas —en paralelo con el cron— se usa
una tabla hija en vez de un JSONB: un `UPDATE` de una fila no pisa a los demás,
mientras que reescribir un array entero sí.

`image_path`/`image_url` SE CONSERVAN como espejo de la diapositiva 0. Así el
flujo de foto única sigue funcionando exactamente igual y el rollback no pierde
datos.

Revision ID: igmedia2026_01
Revises: igsched2026_01
"""
from alembic import op
import sqlalchemy as sa

revision = "igmedia2026_01"
down_revision = "igsched2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instagram_queue",
        sa.Column(
            "media_type", sa.String(16), nullable=False, server_default="IMAGE"
        ),
    )
    op.create_check_constraint(
        "ck_instagram_queue_media_type",
        "instagram_queue",
        "media_type IN ('IMAGE','CAROUSEL','REELS')",
    )

    op.create_table(
        "instagram_queue_media",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer,
            sa.ForeignKey("instagram_queue.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(8), nullable=False, server_default="image"),
        # Qué layout la generó: cover | verse | fact | list | timeline | closing
        sa.Column("role", sa.String(16), nullable=True),
        sa.Column("local_path", sa.String(500), nullable=True),
        sa.Column("url", sa.String(700), nullable=True),
        # Guardarlo permite limpiar huérfanos de carruseles fallidos.
        sa.Column("cloudinary_public_id", sa.String(200), nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("duration_s", sa.Float, nullable=True),
        sa.Column("cover_url", sa.String(700), nullable=True),
        sa.Column("ig_container_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('image','video')", name="ck_iqm_kind"),
        # DEFERRABLE: reordenar N diapositivas colisiona a mitad del bucle si la
        # unicidad se comprueba fila a fila.
        sa.UniqueConstraint(
            "item_id", "position", name="uq_instagram_queue_media_item_pos",
            deferrable=True, initially="DEFERRED",
        ),
    )
    op.create_index(
        "ix_instagram_queue_media_item", "instagram_queue_media", ["item_id"]
    )

    # Backfill: todo item ya preparado estrena su fila 0.
    op.execute(
        """
        INSERT INTO instagram_queue_media (item_id, position, kind, role, local_path, url)
        SELECT id, 0, 'image', 'cover', image_path, image_url
          FROM instagram_queue
         WHERE image_path IS NOT NULL OR image_url IS NOT NULL
        """
    )

    op.alter_column("instagram_queue", "media_type", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_instagram_queue_media_item", table_name="instagram_queue_media")
    op.drop_table("instagram_queue_media")
    op.drop_constraint(
        "ck_instagram_queue_media_type", "instagram_queue", type_="check"
    )
    op.drop_column("instagram_queue", "media_type")
