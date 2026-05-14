from pydantic import BaseModel
from typing import List, Optional
from models import ExerciseCategory, ExerciseDifficulty

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class GoogleLoginRequest(BaseModel):
    id_token: str
    email: str | None = None
    username: str | None = None
    google_id: str | None = None
    photo_url: str | None = None

class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str | None = None

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
