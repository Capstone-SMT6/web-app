"""add_indonesian_onboarding_enum_values

Revision ID: d8b7c2a9416e
Revises: e0d179739e3c
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d8b7c2a9416e"
down_revision: Union[str, Sequence[str], None] = "e0d179739e3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_enum_value(enum_name: str, value: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum
                WHERE enumlabel = '{value}'
                AND enumtypid = '{enum_name}'::regtype
            ) THEN
                ALTER TYPE {enum_name} ADD VALUE '{value}';
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for value in (
        "menurunkan_berat_badan",
        "menaikkan_berat_badan",
        "menjaga_kebugaran",
        "membentuk_otot",
    ):
        _add_enum_value("goalenum", value)

    for value in ("pria", "wanita"):
        _add_enum_value("genderenum", value)

    for value in ("pemula", "menengah", "ahli"):
        _add_enum_value("skilllevelenum", value)

    for value in ("rendah", "sedang", "tinggi"):
        _add_enum_value("intensityenum", value)


def downgrade() -> None:
    # PostgreSQL cannot remove enum values safely without rebuilding the type.
    pass
