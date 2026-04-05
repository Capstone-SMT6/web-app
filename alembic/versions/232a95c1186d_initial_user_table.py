"""initial_user_table

Revision ID: 232a95c1186d
Revises:
Create Date: 2026-04-05 08:14:30.483345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '232a95c1186d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password', sa.String(), nullable=True),
        sa.Column('authProvider', sa.String(), nullable=False),
        sa.Column('googleId', sa.String(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('googleId'),
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)
    # Drop the old table that was managed by the previous ORM
    op.drop_index('User_email_key', table_name='User', if_exists=True)
    op.drop_index('User_googleId_key', table_name='User', if_exists=True)
    op.drop_table('User')


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy.dialects import postgresql
    op.create_table(
        'User',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('username', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('password', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('email', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('createdAt', postgresql.TIMESTAMP(precision=3), server_default=sa.text('CURRENT_TIMESTAMP'), autoincrement=False, nullable=False),
        sa.Column('updatedAt', postgresql.TIMESTAMP(precision=3), autoincrement=False, nullable=False),
        sa.Column('authProvider', sa.TEXT(), server_default=sa.text("'local'::text"), autoincrement=False, nullable=False),
        sa.Column('googleId', sa.TEXT(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('User_pkey')),
    )
    op.create_index('User_googleId_key', 'User', ['googleId'], unique=True)
    op.create_index('User_email_key', 'User', ['email'], unique=True)
    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
