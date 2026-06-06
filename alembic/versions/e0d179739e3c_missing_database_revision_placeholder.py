"""missing_database_revision_placeholder

Revision ID: e0d179739e3c
Revises: 2f6ca54a39dc
Create Date: 2026-06-06 00:00:00.000000

This placeholder preserves the migration chain for databases that were already
stamped with e0d179739e3c, but whose migration file is missing from this repo.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "e0d179739e3c"
down_revision: Union[str, Sequence[str], None] = "2f6ca54a39dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
