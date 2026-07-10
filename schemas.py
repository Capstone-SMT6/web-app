from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import date as datetime_date
from models import ExerciseCategory, ExerciseDifficulty

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class GoogleLoginRequest(BaseModel):
    email: str
    username: str
    google_id: str
    photo_url: str | None = None

class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str | None = None
    notificationEnabled: bool | None = None


class OnboardingSubmit(BaseModel):
    goal: str
    gender: str
    age: int = Field(ge=15)
    height: float = Field(gt=0)
    weight: float = Field(gt=0)
    skill_level: str
    intensity: str
    selected_days: List[str]

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, value: str) -> str:
        valid = {
            "menurunkan_berat_badan",
            "menaikkan_berat_badan",
            "menjaga_kebugaran",
            "membentuk_otot",
        }
        if value not in valid:
            raise ValueError("Invalid goal")
        return value

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, value: str) -> str:
        if value not in {"pria", "wanita"}:
            raise ValueError("Invalid gender")
        return value

    @field_validator("skill_level")
    @classmethod
    def validate_skill_level(cls, value: str) -> str:
        if value not in {"pemula", "menengah", "ahli"}:
            raise ValueError("Invalid skill level")
        return value

    @field_validator("intensity")
    @classmethod
    def validate_intensity(cls, value: str) -> str:
        if value not in {"rendah", "sedang", "tinggi"}:
            raise ValueError("Invalid intensity")
        return value

    @field_validator("selected_days")
    @classmethod
    def validate_selected_days(cls, value: List[str]) -> List[str]:
        valid = {"senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"}
        if len(set(value)) != len(value):
            raise ValueError("Selected days must be unique")
        if any(day not in valid for day in value):
            raise ValueError("Invalid selected day")
        return value

class ExerciseCreate(BaseModel):
    name: str
    slug: str
    description: str
    category: ExerciseCategory
    muscleGroups: List[str]
    secondaryMuscles: List[str] = []
    equipmentRequired: List[str] = []
    difficulty: ExerciseDifficulty
    instructions: List[str]
    tips: List[str] = []
    imageUrl: Optional[str] = None
    videoUrl: Optional[str] = None
    isActive: bool = True

class ExerciseUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    category: Optional[ExerciseCategory] = None
    muscleGroups: Optional[List[str]] = None
    secondaryMuscles: Optional[List[str]] = None
    equipmentRequired: Optional[List[str]] = None
    difficulty: Optional[ExerciseDifficulty] = None
    instructions: Optional[List[str]] = None
    tips: Optional[List[str]] = None
    imageUrl: Optional[str] = None
    videoUrl: Optional[str] = None
    isActive: Optional[bool] = None


class OTPSendRequest(BaseModel):
    email: str
    purpose: str


class OTPVerifyRequest(BaseModel):
    email: str
    code: str
    purpose: str


class PasswordResetRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class WorkoutLogExercise(BaseModel):
    exercise_name: str
    sets_completed: int
    reps_completed: int
    duration_seconds: int = 0
    form_mistakes: Optional[dict] = None


class WorkoutLogRequest(BaseModel):
    duration_seconds: int = 0
    exercises: List[WorkoutLogExercise]


# Section 4: Nutrition Tracking Schemas

class FoodItemCreate(BaseModel):
    name: str
    category: str  # "makanan" | "minuman" | "snack"
    calories_per_serving: float
    protein_per_serving: float
    carbs_per_serving: float
    fat_per_serving: float
    serving_unit: str
    serving_size_g: Optional[float] = None
    imageUrl: Optional[str] = None
    isActive: bool = True

class FoodItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    calories_per_serving: Optional[float] = None
    protein_per_serving: Optional[float] = None
    carbs_per_serving: Optional[float] = None
    fat_per_serving: Optional[float] = None
    serving_unit: Optional[str] = None
    serving_size_g: Optional[float] = None
    imageUrl: Optional[str] = None
    isActive: Optional[bool] = None

class FoodLogCreate(BaseModel):
    food_item_id: str
    quantity: float
    meal_type: str  # "breakfast" | "lunch" | "dinner" | "snack"
    notes: Optional[str] = None
    date: Optional[datetime_date] = None

    @field_validator("meal_type")
    @classmethod
    def validate_meal_type(cls, value: str) -> str:
        if value not in {"breakfast", "lunch", "dinner", "snack"}:
            raise ValueError("Invalid meal type")
        return value

# Section 5: AI Insights
class InsightsModel(BaseModel):
    wawasan_ai: str
    fokus_hari_ini: List[str]

class DashboardReportResponse(BaseModel):
    insights: InsightsModel
    weekly_activity: List[float]
    goals_progress: dict[str, float]


class FCMTokenUpdate(BaseModel):
    fcm_token: str

