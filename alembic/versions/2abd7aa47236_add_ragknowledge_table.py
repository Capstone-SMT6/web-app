"""add_ragknowledge_table

Revision ID: 2abd7aa47236
Revises: adf1650e9612
Create Date: 2026-06-21 21:50:51.315610

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector


# revision identifiers, used by Alembic.
revision: str = '2abd7aa47236'
down_revision: Union[str, Sequence[str], None] = 'adf1650e9612'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.create_table('ragknowledge',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(3072), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ragknowledge')

