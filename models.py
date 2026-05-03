from typing import Optional, List
from datetime import datetime, date, timezone
from enum import Enum
from sqlmodel import Field, SQLModel, Column
from sqlalchemy import UniqueConstraint, JSON, Text
from sqlalchemy.sql import func
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

class GenderEnum(str, Enum):
    male = "male"
    female = "female"


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

class ChatRoleEnum(str, Enum):
    user = "user"
    system = "system"
    assistant = "assistant"

class ExerciseCategory(str, Enum):
    strength = "strength"
    cardio = "cardio"
    flexibility = "flexibility"
    balance = "balance"
    recovery = "recovery"

class ExerciseDifficulty(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"

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
    authProvider: str = Field(default=AuthProvider.email, sa_column_kwargs={"name": "auth_provider"})
    googleId: Optional[str] = Field(default=None, unique=True, sa_column_kwargs={"name": "google_id"})
    photoUrl: Optional[str] = Field(default=None, sa_column_kwargs={"name": "photo_url"})
    notificationEnabled: bool = Field(default=True, sa_column_kwargs={"name": "notification_enabled"})
    deletedAt: Optional[datetime] = Field(default=None, sa_column_kwargs={"name": "deleted_at"})
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "updated_at"})


class UserStats(SQLModel, table=True):
    __tablename__ = "userstats"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", unique=True, index=True)
    currentStreak: int = Field(default=0, sa_column_kwargs={"name": "current_streak"})
    longestStreak: int = Field(default=0, sa_column_kwargs={"name": "longest_streak"})
    lastActiveDate: Optional[date] = Field(default=None, sa_column_kwargs={"name": "last_active_date"})
    totalPushUps: int = Field(default=0, sa_column_kwargs={"name": "total_push_ups"})
    totalSitUps: int = Field(default=0, sa_column_kwargs={"name": "total_sit_ups"})
    updatedAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "updated_at"})


class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "passwordresettoken"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    token: str = Field(index=True)
    expiresAt: datetime = Field(sa_column_kwargs={"name": "expires_at"})
    usedAt: Optional[datetime] = Field(default=None, sa_column_kwargs={"name": "used_at"})
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})


# ---------------------------------------------------------------------------
# Section 2: Onboarding & Exercise Plan
# ---------------------------------------------------------------------------

class UserFitnessProfile(SQLModel, table=True):
    __tablename__ = "userfitnessprofile"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", unique=True, index=True)
    goal: GoalEnum = Field()
    age: int
    gender: GenderEnum = Field()
    height: float
    weight: float
    skillLevel: SkillLevelEnum = Field(sa_column_kwargs={"name": "skill_level"})
    intensity: IntensityEnum = Field()
    equipment: List[str] = Field(default=[], sa_column=Column("equipment", JSON))
    fcsScoreRaw: int = Field(default=0, sa_column_kwargs={"name": "fcs_score_raw"})
    difficultyLevel: DifficultyLevelEnum = Field(sa_column_kwargs={"name": "difficulty_level"})
    bmr: float = Field(default=0.0)
    tdee: float = Field(default=0.0)
    target_daily_kcal: float = Field(default=0.0)
    macros_json: dict = Field(default={}, sa_column=Column(JSON))
    difficulty_gate_applied: bool = Field(default=False)
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "updated_at"})


class ExercisePlan(SQLModel, table=True):
    __tablename__ = "exerciseplan"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    fitness_profile_id: str = Field(foreign_key="userfitnessprofile.id")
    is_active: bool = Field(default=True)
    goal: GoalEnum = Field()
    days_per_week: int
    start_date: date
    difficulty_level: DifficultyLevelEnum = Field()
    applied_constraints: List[str] = Field(default=[], sa_column=Column("applied_constraints", JSON))
    previous_plan_id: Optional[str] = Field(default=None, foreign_key="exerciseplan.id")
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "updated_at"})

class PlanDay(SQLModel, table=True):
    __tablename__ = "plan_day"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    plan_id: str = Field(foreign_key="exerciseplan.id", index=True)
    day_of_week: int = Field(ge=0, le=6)  # 0=Monday, 6=Sunday
    is_rest_day: bool = Field(default=False)
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})


class PlanDayExercise(SQLModel, table=True):
    __tablename__ = "plan_day_exercise"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    plan_day_id: str = Field(foreign_key="plan_day.id", index=True)
    exercise_id: uuid.UUID = Field(foreign_key="exercise.id")
    order: int
    target_sets: int
    target_reps: Optional[int] = Field(default=None)
    target_duration_seconds: Optional[int] = Field(default=None)
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})


class Exercise(SQLModel, table=True):
    __tablename__ = "exercise"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Identity
    name: str = Field(max_length=255, index=True)
    slug: str = Field(max_length=255, unique=True, index=True)  # untuk URL/search
    description: str
    
    # Categorization
    category: ExerciseCategory
    muscleGroups: List[str] = Field(sa_column=Column("muscle_groups", JSON))        # primary muscles
    secondaryMuscles: List[str] = Field(default=[], sa_column=Column("secondary_muscles", JSON))
    equipmentRequired: List[str] = Field(default=[], sa_column=Column("equipment_required", JSON))
    
    # Gating
    difficulty: ExerciseDifficulty
    
    # Guidance
    instructions: List[str] = Field(sa_column=Column(JSON))  # step by step
    tips: List[str] = Field(default=[], sa_column=Column(JSON))  # common mistakes
    
    # Media
    imageUrl: Optional[str] = Field(default=None, sa_column_kwargs={"name": "image_url"})
    videoUrl: Optional[str] = Field(default=None, sa_column_kwargs={"name": "video_url"})
    
    # Meta
    isActive: bool = Field(default=True, sa_column_kwargs={"name": "is_active"})
    
    createdAt: datetime = Field(
        default_factory=now_utc,
        sa_column_kwargs={"server_default": func.now(), "name": "created_at"}
    )
    
    updatedAt: datetime = Field(
        default_factory=now_utc,
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),
            "name": "updated_at"
        }
    )


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
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})


class ExerciseLog(SQLModel, table=True):
    """One row = one set performed in a session."""
    __tablename__ = "exerciselog"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    session_id: str = Field(foreign_key="workoutsession.id", index=True)
    exercise_id: uuid.UUID = Field(foreign_key="exercise.id")
    set_number: int
    reps_completed: int
    is_manual_input: bool = Field(default=False)
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})


class DailyLog(SQLModel, table=True):
    """Source of truth for streak calculation. UNIQUE(user_id, date)."""
    __tablename__ = "dailylog"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_dailylog_user_date"),)

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    date: date
    day_type: str = Field()
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})


# ---------------------------------------------------------------------------
# Section 5: Chatbot
# ---------------------------------------------------------------------------

class ChatSession(SQLModel, table=True):
    __tablename__ = "chatsession"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    title: str = Field(default="New Chat")
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})
    updatedAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "updated_at"})


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chatmessage"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)
    role: str = Field()
    text: str = Field(sa_column=Column(Text))
    sources: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    createdAt: datetime = Field(default_factory=now_utc, sa_column_kwargs={"name": "created_at"})
