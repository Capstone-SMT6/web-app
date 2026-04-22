"""schema_v3_full_rebuild

Revision ID: 8b2328d92477
Revises: c6fab1ed72bb
Create Date: 2026-04-22 09:07:00.906131

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '8b2328d92477'
down_revision: Union[str, Sequence[str], None] = 'c6fab1ed72bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — drops old integer-PK tables and rebuilds with UUID PKs."""

    # --- Drop old tables (integer PK era) in FK-safe order ---
    op.drop_table('chatmessage')
    op.drop_table('chatsession')
    op.drop_table('user')

    # --- Section 1: Auth & Profile ---
    op.create_table('badge',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('requirement', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('iconUrl', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('user',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('password', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('authProvider', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('googleId', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('photoUrl', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('notificationEnabled', sa.Boolean(), nullable=False),
        sa.Column('activeBadgeId', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('deletedAt', sa.DateTime(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['activeBadgeId'], ['badge.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('googleId'),
    )
    op.create_index(op.f('ix_user_username'), 'user', ['username'], unique=True)

    op.create_table('userstats',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('currentLevel', sa.Integer(), nullable=False),
        sa.Column('totalXp', sa.Integer(), nullable=False),
        sa.Column('currentStreak', sa.Integer(), nullable=False),
        sa.Column('longestStreak', sa.Integer(), nullable=False),
        sa.Column('lastActiveDate', sa.Date(), nullable=True),
        sa.Column('totalPushUps', sa.Integer(), nullable=False),
        sa.Column('totalSitUps', sa.Integer(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_userstats_user_id'), 'userstats', ['user_id'], unique=True)

    op.create_table('passwordresettoken',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('token', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('expiresAt', sa.DateTime(), nullable=False),
        sa.Column('usedAt', sa.DateTime(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_passwordresettoken_user_id'), 'passwordresettoken', ['user_id'], unique=False)
    op.create_index(op.f('ix_passwordresettoken_token'), 'passwordresettoken', ['token'], unique=False)

    # --- Section 2: Onboarding & Exercise Plan ---
    op.create_table('userfitnessprofile',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('goal', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('durationTarget', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('age', sa.Integer(), nullable=False),
        sa.Column('height', sa.Float(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('skillLevel', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('intensity', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('equipment', sa.JSON(), nullable=True),
        sa.Column('activeInjuries', sa.JSON(), nullable=True),
        sa.Column('fcsScoreRaw', sa.Integer(), nullable=False),
        sa.Column('fcsScoreDowngraded', sa.Integer(), nullable=False),
        sa.Column('difficultyLevel', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_userfitnessprofile_user_id'), 'userfitnessprofile', ['user_id'], unique=True)

    op.create_table('exercise',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('base_xp', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('tutorialUrl', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('exerciseplan',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('fitness_profile_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('goal', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('duration_target', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('days_per_week', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('difficulty_level', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('schedule_json', sa.JSON(), nullable=True),
        sa.Column('applied_constraints', sa.JSON(), nullable=True),
        sa.Column('previous_plan_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('progression_modifier', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fitness_profile_id'], ['userfitnessprofile.id']),
        sa.ForeignKeyConstraint(['previous_plan_id'], ['exerciseplan.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exerciseplan_user_id'), 'exerciseplan', ['user_id'], unique=False)

    # --- Section 3: Workout Tracking ---
    op.create_table('workoutsession',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('plan_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('total_xp_earned', sa.Integer(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['exerciseplan.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workoutsession_user_id'), 'workoutsession', ['user_id'], unique=False)

    op.create_table('exerciselog',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('exercise_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('set_number', sa.Integer(), nullable=False),
        sa.Column('reps_completed', sa.Integer(), nullable=False),
        sa.Column('is_manual_input', sa.Boolean(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercise.id']),
        sa.ForeignKeyConstraint(['session_id'], ['workoutsession.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exerciselog_session_id'), 'exerciselog', ['session_id'], unique=False)

    op.create_table('dailylog',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('day_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='uq_dailylog_user_date')
    )
    op.create_index(op.f('ix_dailylog_user_id'), 'dailylog', ['user_id'], unique=False)

    # --- Section 4: Gamification ---
    op.create_table('achievement',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('condition_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('required_value', sa.Integer(), nullable=False),
        sa.Column('xp_reward', sa.Integer(), nullable=False),
        sa.Column('iconUrl', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('userachievement',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('achievement_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('earnedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['achievement_id'], ['achievement.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'achievement_id', name='uq_userachievement')
    )
    op.create_index(op.f('ix_userachievement_user_id'), 'userachievement', ['user_id'], unique=False)

    op.create_table('userbadge',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('badge_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('earnedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['badge_id'], ['badge.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'badge_id', name='uq_userbadge')
    )
    op.create_index(op.f('ix_userbadge_user_id'), 'userbadge', ['user_id'], unique=False)

    op.create_table('personalrecord',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('exercise_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('best_reps_in_session', sa.Integer(), nullable=False),
        sa.Column('achieved_at', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercise.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'exercise_id', name='uq_personalrecord')
    )
    op.create_index(op.f('ix_personalrecord_user_id'), 'personalrecord', ['user_id'], unique=False)

    op.create_table('leaderboardsnapshot',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('exercise_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('total_reps', sa.Integer(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'week_start', 'exercise_type', name='uq_leaderboard_snapshot')
    )
    op.create_index(op.f('ix_leaderboardsnapshot_user_id'), 'leaderboardsnapshot', ['user_id'], unique=False)

    # --- Section 5: Chatbot ---
    op.create_table('chatsession',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chatsession_user_id'), 'chatsession', ['user_id'], unique=False)

    op.create_table('chatmessage',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chatsession.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chatmessage_session_id'), 'chatmessage', ['session_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema — drops all v3 tables."""
    op.drop_index(op.f('ix_chatmessage_session_id'), table_name='chatmessage')
    op.drop_table('chatmessage')
    op.drop_index(op.f('ix_chatsession_user_id'), table_name='chatsession')
    op.drop_table('chatsession')
    op.drop_index(op.f('ix_leaderboardsnapshot_user_id'), table_name='leaderboardsnapshot')
    op.drop_table('leaderboardsnapshot')
    op.drop_index(op.f('ix_personalrecord_user_id'), table_name='personalrecord')
    op.drop_table('personalrecord')
    op.drop_index(op.f('ix_userbadge_user_id'), table_name='userbadge')
    op.drop_table('userbadge')
    op.drop_index(op.f('ix_userachievement_user_id'), table_name='userachievement')
    op.drop_table('userachievement')
    op.drop_table('achievement')
    op.drop_index(op.f('ix_dailylog_user_id'), table_name='dailylog')
    op.drop_table('dailylog')
    op.drop_index(op.f('ix_exerciselog_session_id'), table_name='exerciselog')
    op.drop_table('exerciselog')
    op.drop_index(op.f('ix_workoutsession_user_id'), table_name='workoutsession')
    op.drop_table('workoutsession')
    op.drop_index(op.f('ix_exerciseplan_user_id'), table_name='exerciseplan')
    op.drop_table('exerciseplan')
    op.drop_table('exercise')
    op.drop_index(op.f('ix_userfitnessprofile_user_id'), table_name='userfitnessprofile')
    op.drop_table('userfitnessprofile')
    op.drop_index(op.f('ix_passwordresettoken_token'), table_name='passwordresettoken')
    op.drop_index(op.f('ix_passwordresettoken_user_id'), table_name='passwordresettoken')
    op.drop_table('passwordresettoken')
    op.drop_index(op.f('ix_userstats_user_id'), table_name='userstats')
    op.drop_table('userstats')
    op.drop_index(op.f('ix_user_username'), table_name='user')
    op.drop_table('user')
    op.drop_table('badge')
