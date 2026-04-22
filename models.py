from typing import Optional, List
from datetime import datetime, date, timezone
from enum import Enum
from sqlmodel import Field, SQLModel, Column
from sqlalchemy import UniqueConstraint, JSON, Text
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AuthProvider(str, Enum):
    email = "email"
    google = "google"


class GoalEnum(str, Enum):
    weight_loss = "weight_loss"
    muscle_gain = "muscle_gain"
    maintain = "maintain"


class DurationTargetEnum(str, Enum):
    one_month = "1_month"
    three_months = "3_months"
    six_months = "6_months"
    long_term = "long_term"


class SkillLevelEnum(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class IntensityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class DifficultyLevelEnum(str, Enum):
    level_1 = "level_1"
    level_2 = "level_2"
    level_3 = "level_3"


class ProgressionModifierEnum(str, Enum):
    aggressive = "aggressive"
    standard = "standard"
    conservative = "conservative"
    very_conservative = "very_conservative"


class ExerciseTypeEnum(str, Enum):
    push_up = "push_up"
    sit_up = "sit_up"
    crunch = "crunch"
    knee_push_up = "knee_push_up"
    wall_push_up = "wall_push_up"
    decline_push_up = "decline_push_up"
    knuckle_push_up = "knuckle_push_up"


class DayTypeEnum(str, Enum):
    workout_completed = "workout_completed"
    rest_day = "rest_day"
    missed = "missed"


class AchievementCategoryEnum(str, Enum):
    first_session = "first_session"
    push_up = "push_up"
    sit_up = "sit_up"
    streak = "streak"
    leaderboard = "leaderboard"


class AchievementConditionTypeEnum(str, Enum):
    lifetime_total = "lifetime_total"
    single_session = "single_session"
    streak_days = "streak_days"
    first_session = "first_session"
    leaderboard_rank = "leaderboard_rank"


class LeaderboardExerciseTypeEnum(str, Enum):
    push_up = "push_up"
    sit_up = "sit_up"


class ChatRoleEnum(str, Enum):
    user = "user"
    system = "system"
    assistant = "assistant"


# ---------------------------------------------------------------------------
# Section 1: Auth & Profile
# ---------------------------------------------------------------------------

class User(SQLModel, table=True):
    __tablename__ = "user"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    password: Optional[str] = Field(default=None)
    is_admin: bool = Field(default=False)
    authProvider: str = Field(default=AuthProvider.email)
    googleId: Optional[str] = Field(default=None, unique=True)
    photoUrl: Optional[str] = Field(default=None)
    notificationEnabled: bool = Field(default=True)
    activeBadgeId: Optional[str] = Field(default=None, foreign_key="badge.id")
    deletedAt: Optional[datetime] = Field(default=None)
    createdAt: datetime = Field(default_factory=now_utc)
    updatedAt: datetime = Field(default_factory=now_utc)


class UserStats(SQLModel, table=True):
    __tablename__ = "userstats"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", unique=True, index=True)
    currentLevel: int = Field(default=1)
    totalXp: int = Field(default=0)
    currentStreak: int = Field(default=0)
    longestStreak: int = Field(default=0)
    lastActiveDate: Optional[date] = Field(default=None)
    totalPushUps: int = Field(default=0)
    totalSitUps: int = Field(default=0)
    updatedAt: datetime = Field(default_factory=now_utc)


class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "passwordresettoken"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    token: str = Field(index=True)
    expiresAt: datetime
    usedAt: Optional[datetime] = Field(default=None)
    createdAt: datetime = Field(default_factory=now_utc)


# ---------------------------------------------------------------------------
# Section 2: Onboarding & Exercise Plan
# ---------------------------------------------------------------------------

class UserFitnessProfile(SQLModel, table=True):
    __tablename__ = "userfitnessprofile"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", unique=True, index=True)
    goal: str = Field()
    durationTarget: str = Field()
    age: int
    height: float
    weight: float
    skillLevel: str = Field()
    intensity: str = Field()
    equipment: List[str] = Field(default=[], sa_column=Column(JSON))
    activeInjuries: List[str] = Field(default=[], sa_column=Column(JSON))
    fcsScoreRaw: int = Field(default=0)
    fcsScoreDowngraded: int = Field(default=0)
    difficultyLevel: str = Field()
    createdAt: datetime = Field(default_factory=now_utc)
    updatedAt: datetime = Field(default_factory=now_utc)


class ExercisePlan(SQLModel, table=True):
    __tablename__ = "exerciseplan"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    fitness_profile_id: str = Field(foreign_key="userfitnessprofile.id")
    is_active: bool = Field(default=True)
    goal: str = Field()
    duration_target: str = Field()
    days_per_week: int
    start_date: date
    difficulty_level: str = Field()
    schedule_json: dict = Field(default={}, sa_column=Column(JSON))
    applied_constraints: List[str] = Field(default=[], sa_column=Column(JSON))
    previous_plan_id: Optional[str] = Field(default=None, foreign_key="exerciseplan.id")
    progression_modifier: str = Field()
    createdAt: datetime = Field(default_factory=now_utc)
    updatedAt: datetime = Field(default_factory=now_utc)


class Exercise(SQLModel, table=True):
    __tablename__ = "exercise"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    name: str
    type: str = Field()
    base_xp: int = Field(default=1)
    description: str = Field(sa_column=Column(Text))
    tutorialUrl: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# Section 3: Workout Tracking
# ---------------------------------------------------------------------------

class WorkoutSession(SQLModel, table=True):
    __tablename__ = "workoutsession"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    plan_id: Optional[str] = Field(default=None, foreign_key="exerciseplan.id")
    date: date
    duration_seconds: int = Field(default=0)
    total_xp_earned: int = Field(default=0)
    createdAt: datetime = Field(default_factory=now_utc)


class ExerciseLog(SQLModel, table=True):
    """One row = one set performed in a session."""
    __tablename__ = "exerciselog"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    session_id: str = Field(foreign_key="workoutsession.id", index=True)
    exercise_id: str = Field(foreign_key="exercise.id")
    set_number: int
    reps_completed: int
    is_manual_input: bool = Field(default=False)
    createdAt: datetime = Field(default_factory=now_utc)


class DailyLog(SQLModel, table=True):
    """Source of truth for streak calculation. UNIQUE(user_id, date)."""
    __tablename__ = "dailylog"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_dailylog_user_date"),)

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    date: date
    day_type: str = Field()
    createdAt: datetime = Field(default_factory=now_utc)


# ---------------------------------------------------------------------------
# Section 4: Gamification
# ---------------------------------------------------------------------------

class Achievement(SQLModel, table=True):
    __tablename__ = "achievement"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    title: str
    description: str = Field(sa_column=Column(Text))
    category: str = Field()
    condition_type: str = Field()
    required_value: int
    xp_reward: int = Field(default=0)
    iconUrl: Optional[str] = Field(default=None)


class UserAchievement(SQLModel, table=True):
    """UNIQUE(user_id, achievement_id) — each achievement earned only once."""
    __tablename__ = "userachievement"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", name="uq_userachievement"),)

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    achievement_id: str = Field(foreign_key="achievement.id")
    earnedAt: datetime = Field(default_factory=now_utc)


class Badge(SQLModel, table=True):
    __tablename__ = "badge"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    name: str
    description: str = Field(sa_column=Column(Text))
    requirement: str
    iconUrl: Optional[str] = Field(default=None)


class UserBadge(SQLModel, table=True):
    """UNIQUE(user_id, badge_id) — each badge earned only once."""
    __tablename__ = "userbadge"
    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_userbadge"),)

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    badge_id: str = Field(foreign_key="badge.id")
    earnedAt: datetime = Field(default_factory=now_utc)


class PersonalRecord(SQLModel, table=True):
    """Best reps in a single set per exercise, ever. UNIQUE(user_id, exercise_id)."""
    __tablename__ = "personalrecord"
    __table_args__ = (UniqueConstraint("user_id", "exercise_id", name="uq_personalrecord"),)

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    exercise_id: str = Field(foreign_key="exercise.id")
    best_reps_in_session: int
    achieved_at: datetime = Field(default_factory=now_utc)
    updatedAt: datetime = Field(default_factory=now_utc)


class LeaderboardSnapshot(SQLModel, table=True):
    """Frozen weekly ranking. UNIQUE(user_id, week_start, exercise_type)."""
    __tablename__ = "leaderboardsnapshot"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", "exercise_type", name="uq_leaderboard_snapshot"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    week_start: date
    exercise_type: str = Field()
    total_reps: int
    rank: int
    createdAt: datetime = Field(default_factory=now_utc)


# ---------------------------------------------------------------------------
# Section 5: Chatbot
# ---------------------------------------------------------------------------

class ChatSession(SQLModel, table=True):
    __tablename__ = "chatsession"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    title: str = Field(default="New Chat")
    createdAt: datetime = Field(default_factory=now_utc)
    updatedAt: datetime = Field(default_factory=now_utc)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chatmessage"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)
    role: str = Field()
    text: str = Field(sa_column=Column(Text))
    sources: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    createdAt: datetime = Field(default_factory=now_utc)
