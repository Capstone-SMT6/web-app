from typing import List
import jwt
import random
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from models import (
    DailyLog,
    DifficultyLevelEnum,
    ExercisePlan,
    GenderEnum,
    GoalEnum,
    IntensityEnum,
    OTPVerification,
    PlanDay,
    SkillLevelEnum,
    User,
    UserFitnessProfile,
    UserStats,
    WorkoutSession,
    ExerciseLog,
)
from database import get_session
from schemas import (
    GoogleLoginRequest,
    OnboardingSubmit,
    UserCreate,
    UserLogin,
    UserUpdate,
    OTPSendRequest,
    OTPVerifyRequest,
    PasswordResetRequest,
    ChangePasswordRequest,
    WorkoutLogRequest,
    DashboardReportResponse,
    FCMTokenUpdate,
)
import bcrypt
import os
from dotenv import load_dotenv
from cloudinary_storage import upload_image_to_cloudinary

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Please add it to your .env file before starting the server."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 43200

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        raise credentials_exception
    return user


router = APIRouter(
    prefix="/api/users",
    tags=["users"],
)


DAY_INDEX = {
    "senin": 0,
    "selasa": 1,
    "rabu": 2,
    "kamis": 3,
    "jumat": 4,
    "sabtu": 5,
    "minggu": 6,
}


def _validate_training_days(intensity: str, selected_days: list[str]) -> None:
    count = len(selected_days)
    if intensity == "rendah" and count != 3:
        raise HTTPException(status_code=400, detail="Intensitas rendah harus memilih 3 hari latihan")
    if intensity == "sedang" and count != 4:
        raise HTTPException(status_code=400, detail="Intensitas sedang harus memilih 4 hari latihan")
    if intensity == "tinggi" and count not in {5, 6}:
        raise HTTPException(status_code=400, detail="Intensitas tinggi harus memilih 5 atau 6 hari latihan")


def _calculate_onboarding(payload: OnboardingSubmit) -> dict:
    applied_constraints: list[str] = []

    height_m = payload.height / 100
    bmi = round(payload.weight / (height_m**2), 1)
    bmi_score = 20 if 18.5 <= bmi < 25 else (15 if 25 <= bmi < 30 else (10 if bmi < 18.5 else 5))
    age_score = 20 if 15 <= payload.age <= 30 else (10 if 31 <= payload.age <= 45 else 0)
    fcs_score = bmi_score + age_score

    if fcs_score >= 31:
        capacity = "ahli"
    elif fcs_score >= 16:
        capacity = "menengah"
    else:
        capacity = "pemula"

    difficulty = capacity
    if payload.skill_level == "pemula":
        if capacity == "ahli":
            difficulty = "menengah"
            applied_constraints.append("Gate: Fisik ahli tapi teknik pemula, level di-cap ke menengah.")
        elif fcs_score >= 25:
            difficulty = "menengah"
            applied_constraints.append("Gate: Fisik mumpuni, pemula dinaikkan ke menengah.")
        else:
            difficulty = "pemula"
    elif payload.skill_level == "menengah" and capacity == "pemula":
        difficulty = "pemula"
        applied_constraints.append("Gate: Fisik terlalu rendah untuk menengah, level diturunkan ke pemula.")
    elif payload.skill_level == "ahli" and capacity == "pemula":
        difficulty = "menengah"
        applied_constraints.append("Gate: Kapasitas fisik rendah, ahli dibantu ke menengah.")

    bmr = (10 * payload.weight) + (6.25 * payload.height) - (5 * payload.age)
    bmr += 5 if payload.gender == "pria" else -161

    activity_multiplier = {"rendah": 1.375, "sedang": 1.55, "tinggi": 1.725}[payload.intensity]
    tdee = round(bmr * activity_multiplier)

    effective_goal = payload.goal
    if bmi < 18.5 and payload.goal == "menurunkan_berat_badan":
        effective_goal = "menjaga_kebugaran"
        applied_constraints.append("Goal override: berat badan kurang tidak diperbolehkan menurunkan berat badan.")

    if effective_goal == "menurunkan_berat_badan":
        target_kcal = tdee - 500
    elif effective_goal in {"menaikkan_berat_badan", "membentuk_otot"}:
        target_kcal = tdee + 300
    else:
        target_kcal = tdee

    floor = 1500 if payload.gender == "pria" else 1200
    if target_kcal < floor:
        target_kcal = floor
        applied_constraints.append(f"Calorie floor: target dinaikkan ke batas aman {floor} kkal.")

    macro_ratios = {
        "menurunkan_berat_badan": {"protein": 0.35, "carbs": 0.40, "fat": 0.25},
        "menaikkan_berat_badan": {"protein": 0.30, "carbs": 0.45, "fat": 0.25},
        "menjaga_kebugaran": {"protein": 0.25, "carbs": 0.50, "fat": 0.25},
        "membentuk_otot": {"protein": 0.30, "carbs": 0.45, "fat": 0.25},
    }[effective_goal]

    difficulty_map = {
        "pemula": DifficultyLevelEnum.level_1,
        "menengah": DifficultyLevelEnum.level_2,
        "ahli": DifficultyLevelEnum.level_3,
    }

    return {
        "goal": effective_goal,
        "fcs_score": fcs_score,
        "difficulty_level": difficulty_map[difficulty],
        "bmr": round(bmr),
        "tdee": tdee,
        "target_daily_kcal": round(target_kcal),
        "macros_json": {
            "protein_g": round(target_kcal * macro_ratios["protein"] / 4),
            "carbs_g": round(target_kcal * macro_ratios["carbs"] / 4),
            "fat_g": round(target_kcal * macro_ratios["fat"] / 9),
        },
        "difficulty_gate_applied": any(item.startswith("Gate:") for item in applied_constraints),
        "applied_constraints": applied_constraints,
    }


def _exercise_targets(goal: str, difficulty_level: DifficultyLevelEnum) -> list[dict]:
    difficulty_values = {
        DifficultyLevelEnum.level_1: {"sets": 3, "reps": 10, "plank_seconds": 25, "rest": 60},
        DifficultyLevelEnum.level_2: {"sets": 3, "reps": 15, "plank_seconds": 40, "rest": 45},
        DifficultyLevelEnum.level_3: {"sets": 4, "reps": 15, "plank_seconds": 60, "rest": 30},
    }
    values = difficulty_values[difficulty_level].copy()

    if goal == "menurunkan_berat_badan":
        values["reps"] += 3
        values["rest"] = max(25, values["rest"] - 10)
    elif goal == "menaikkan_berat_badan":
        values["rest"] += 15
    elif goal == "membentuk_otot":
        values["sets"] += 1
        values["rest"] += 15

    return [
        {
            "name": "Push-Up",
            "exercise": "push_up",
            "sets": values["sets"],
            "reps": values["reps"],
            "target_duration_seconds": None,
            "rest_seconds": values["rest"],
        },
        {
            "name": "Sit-Up",
            "exercise": "sit_up",
            "sets": values["sets"],
            "reps": values["reps"],
            "target_duration_seconds": None,
            "rest_seconds": values["rest"],
        },
        {
            "name": "Squat",
            "exercise": "squat",
            "sets": values["sets"],
            "reps": values["reps"],
            "target_duration_seconds": None,
            "rest_seconds": values["rest"],
        },
        {
            "name": "Plank",
            "exercise": "plank",
            "sets": values["sets"],
            "reps": None,
            "target_duration_seconds": values["plank_seconds"],
            "rest_seconds": values["rest"],
        },
    ]


def _exercise_targets_for_day(
    goal: str,
    intensity: str,
    difficulty_level: DifficultyLevelEnum,
    active_day_index: int,
) -> list[dict]:
    exercises = _exercise_targets(goal, difficulty_level)
    by_key = {exercise["exercise"]: exercise for exercise in exercises}

    if intensity != "rendah":
        return exercises

    rotations = {
        "menjaga_kebugaran": [
            ["push_up", "squat", "plank"],
            ["sit_up", "squat", "plank"],
            ["push_up", "sit_up", "squat"],
        ],
        "menurunkan_berat_badan": [
            ["push_up", "squat", "plank"],
            ["sit_up", "squat", "plank"],
            ["push_up", "sit_up", "squat"],
        ],
        "menaikkan_berat_badan": [
            ["push_up", "squat", "plank"],
            ["push_up", "sit_up", "squat"],
            ["push_up", "squat", "plank"],
        ],
        "membentuk_otot": [
            ["push_up", "squat", "plank"],
            ["push_up", "sit_up", "squat"],
            ["push_up", "squat", "plank"],
        ],
    }
    day_rotation = rotations.get(goal, rotations["menjaga_kebugaran"])
    selected_keys = day_rotation[active_day_index % len(day_rotation)]
    return [by_key[key] for key in selected_keys]


@router.post("/", response_model=User)
def create_user(user: UserCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == user.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    otp_verified = session.exec(
        select(OTPVerification)
        .where(OTPVerification.email == user.email)
        .where(OTPVerification.purpose == "register")
        .where(OTPVerification.verifiedAt != None)
        .order_by(OTPVerification.verifiedAt.desc())
    ).first()

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if not otp_verified or otp_verified.verifiedAt.replace(tzinfo=None) < now_utc - timedelta(minutes=15):
        raise HTTPException(status_code=400, detail="Email is not verified via OTP")

    hashed_password = get_password_hash(user.password)
    new_user = User(
        username=user.username,
        email=user.email,
        password=hashed_password,
    )
    session.add(new_user)
    session.flush()
    session.add(UserStats(user_id=new_user.id))
    session.commit()
    session.refresh(new_user)
    return new_user


@router.post("/login")
def login_user(user: UserLogin, session: Session = Depends(get_session)):
    db_user = session.exec(select(User).where(User.email == user.email)).first()
    if not db_user or not db_user.password or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": db_user}


@router.post("/google-login")
async def google_login(data: GoogleLoginRequest, session: Session = Depends(get_session)):
    import httpx

    async def upload_google_photo(google_url: str) -> str | None:
        """Download Google profile photo and re-upload to Cloudinary."""
        from urllib.parse import urlparse
        parsed = urlparse(google_url)
        if not parsed.netloc.endswith("googleusercontent.com"):
            return google_url

        try:
            # Upgrade to higher resolution (s400 instead of s100)
            high_res_url = google_url.split("=s")[0] + "=s400-c"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(high_res_url, follow_redirects=True)
            if resp.status_code != 200:
                return google_url  # fallback to original if download fails
            import cloudinary.uploader
            result = cloudinary.uploader.upload(
                resp.content,
                folder="smafit/avatars",
                resource_type="image",
            )
            return result["secure_url"]
        except Exception as e:
            print(f"Failed to re-upload Google photo: {e}")
            return google_url  # fallback to original

    db_user = session.exec(select(User).where(User.email == data.email)).first()
    if not db_user:
        # New user — mirror photo to Cloudinary immediately
        cloudinary_url = None
        if data.photo_url:
            cloudinary_url = await upload_google_photo(data.photo_url)
        db_user = User(
            username=data.username,
            email=data.email,
            authProvider="google",
            googleId=data.google_id,
            photoUrl=cloudinary_url,
        )
        session.add(db_user)
        session.flush()
        session.add(UserStats(user_id=db_user.id))
        session.commit()
        session.refresh(db_user)
    else:
        needs_save = False
        if not db_user.googleId:
            db_user.googleId = data.google_id
            needs_save = True
        # Re-upload only if still pointing at Google's CDN (lh3.googleusercontent)
        if data.photo_url and (
            not db_user.photoUrl or "googleusercontent" in db_user.photoUrl
        ):
            db_user.photoUrl = await upload_google_photo(data.photo_url)
            needs_save = True
        if needs_save:
            db_user.updatedAt = datetime.now(timezone.utc)
            session.add(db_user)
            session.commit()
            session.refresh(db_user)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": db_user}


# ---------------------------------------------------------------------------
# OTP Routes
# ---------------------------------------------------------------------------

@router.post("/otp/send")
def send_otp(request: OTPSendRequest, session: Session = Depends(get_session)):
    if request.purpose == "reset_password":
        user = session.exec(select(User).where(User.email == request.email)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Email is not registered")
    elif request.purpose == "register":
        user = session.exec(select(User).where(User.email == request.email)).first()
        if user:
            raise HTTPException(status_code=400, detail="Email already registered")

    code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    otp_record = OTPVerification(
        email=request.email,
        code=code,
        purpose=request.purpose,
        expiresAt=expires_at
    )
    session.add(otp_record)
    session.commit()

    try:
        from mail_helper import send_otp_email
        send_otp_email(request.email, code, request.purpose)
    except Exception as e:
        print(f"Failed to send email (probably Resend free tier issue). The OTP is: {code}")
        # We don't raise an error here so the app can continue to the OTP screen

    return {"message": "OTP sent successfully"}


@router.post("/otp/verify")
def verify_otp(request: OTPVerifyRequest, session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    otp_record = session.exec(
        select(OTPVerification)
        .where(OTPVerification.email == request.email)
        .where(OTPVerification.purpose == request.purpose)
        .where(OTPVerification.code == request.code)
        .where(OTPVerification.expiresAt > now)
        .where(OTPVerification.verifiedAt == None)
        .order_by(OTPVerification.createdAt.desc())
    ).first()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code")

    otp_record.verifiedAt = now
    session.add(otp_record)
    session.commit()
    return {"message": "OTP verified successfully"}


@router.post("/reset-password")
def reset_password(request: PasswordResetRequest, session: Session = Depends(get_session)):
    otp_verified = session.exec(
        select(OTPVerification)
        .where(OTPVerification.email == request.email)
        .where(OTPVerification.purpose == "reset_password")
        .where(OTPVerification.verifiedAt != None)
        .order_by(OTPVerification.verifiedAt.desc())
    ).first()

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if not otp_verified or otp_verified.verifiedAt.replace(tzinfo=None) < now_utc - timedelta(minutes=15):
        raise HTTPException(status_code=400, detail="OTP code has not been verified for password reset")

    user = session.exec(select(User).where(User.email == request.email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = get_password_hash(request.password)
    user.updatedAt = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return {"message": "Password reset successfully"}


@router.post("/change-password")
def change_password_logged_in(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not current_user.password or not verify_password(request.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Password lama salah")

    current_user.password = get_password_hash(request.new_password)
    current_user.updatedAt = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    return {"message": "Password berhasil diperbarui"}


@router.get("/me", response_model=User)
def read_user_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.post("/me/fcm-token")
def update_fcm_token(
    payload: FCMTokenUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    current_user.fcmToken = payload.fcm_token
    current_user.updatedAt = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    return {"message": "FCM token updated successfully"}



@router.get("/me/stats", response_model=UserStats)
def read_user_stats_me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    stats = session.exec(select(UserStats).where(UserStats.user_id == current_user.id)).first()
    if not stats:
        stats = UserStats(user_id=current_user.id)
        session.add(stats)
        session.commit()
        session.refresh(stats)
    else:
        # Dynamically evaluate streak breakage
        if stats.lastActiveDate:
            today = date.today()
            yesterday = today - timedelta(days=1)
            # If the last active date is older than yesterday, the streak is broken
            if stats.lastActiveDate < yesterday and stats.currentStreak > 0:
                stats.currentStreak = 0
                session.add(stats)
                session.commit()
                session.refresh(stats)

    return stats


@router.get("/me/fitness-profile", response_model=UserFitnessProfile)
def read_user_fitness_profile_me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    profile = session.exec(select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Fitness profile not found")
    return profile


@router.post("/me/fitness-profile", response_model=UserFitnessProfile)
def submit_user_fitness_profile_me(
    payload: OnboardingSubmit,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _validate_training_days(payload.intensity, payload.selected_days)
    calculated = _calculate_onboarding(payload)

    profile = session.exec(
        select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)
    ).first()

    if profile:
        profile.goal = GoalEnum(calculated["goal"])
        profile.age = payload.age
        profile.gender = GenderEnum(payload.gender)
        profile.height = payload.height
        profile.weight = payload.weight
        profile.skillLevel = SkillLevelEnum(payload.skill_level)
        profile.intensity = IntensityEnum(payload.intensity)
        profile.fcsScoreRaw = calculated["fcs_score"]
        profile.difficultyLevel = calculated["difficulty_level"]
        profile.bmr = calculated["bmr"]
        profile.tdee = calculated["tdee"]
        profile.target_daily_kcal = calculated["target_daily_kcal"]
        profile.macros_json = calculated["macros_json"]
        profile.difficulty_gate_applied = calculated["difficulty_gate_applied"]
        profile.updatedAt = datetime.now(timezone.utc)
    else:
        profile = UserFitnessProfile(
            user_id=current_user.id,
            goal=GoalEnum(calculated["goal"]),
            age=payload.age,
            gender=GenderEnum(payload.gender),
            height=payload.height,
            weight=payload.weight,
            skillLevel=SkillLevelEnum(payload.skill_level),
            intensity=IntensityEnum(payload.intensity),
            equipment=[],
            fcsScoreRaw=calculated["fcs_score"],
            difficultyLevel=calculated["difficulty_level"],
            bmr=calculated["bmr"],
            tdee=calculated["tdee"],
            target_daily_kcal=calculated["target_daily_kcal"],
            macros_json=calculated["macros_json"],
            difficulty_gate_applied=calculated["difficulty_gate_applied"],
        )

    session.add(profile)
    session.flush()

    from services.plan_generator import generate_plan
    generate_plan(profile, session, payload.selected_days, applied_constraints=calculated["applied_constraints"])
    session.commit()
    session.refresh(profile)
    return profile


@router.get("/me/exercise-plan")
def read_active_exercise_plan_me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    from services.plan_generator import get_active_plan
    result = get_active_plan(current_user.id, session)
    if not result:
        raise HTTPException(status_code=404, detail="Active exercise plan not found")
    
    # We must also attach nutrition facts from the profile
    plan = session.exec(
        select(ExercisePlan).where(
            ExercisePlan.user_id == current_user.id,
            ExercisePlan.is_active == True,
        )
    ).first()
    
    if plan:
        profile = session.get(UserFitnessProfile, plan.fitness_profile_id)
        if profile:
            result["nutrition"] = {
                "bmr": profile.bmr,
                "tdee": profile.tdee,
                "target_daily_kcal": profile.target_daily_kcal,
                "macros": profile.macros_json,
            }

    return result


@router.get("/me/workout-history")
def get_workout_history(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = 30,
):
    sessions = session.exec(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .order_by(WorkoutSession.date.desc())
        .limit(limit)
    ).all()
    return [
        {"id": s.id, "date": s.date.isoformat(), "duration_seconds": s.duration_seconds}
        for s in sessions
    ]


from fastapi import BackgroundTasks

@router.post("/me/workout-log")
def log_workout(
    payload: WorkoutLogRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    today = date.today()

    # Active plan (optional link)
    plan = session.exec(
        select(ExercisePlan).where(
            ExercisePlan.user_id == current_user.id,
            ExercisePlan.is_active == True,  # noqa: E712
        )
    ).first()

    # Calculate calories burned
    profile = session.exec(select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)).first()
    weight_kg = profile.weight if profile else 65.0
    duration_hours = payload.duration_seconds / 3600.0
    calories_burned = 5.0 * weight_kg * duration_hours

    # Create session record
    workout_session = WorkoutSession(
        user_id=current_user.id,
        plan_id=plan.id if plan else None,
        date=today,
        duration_seconds=payload.duration_seconds,
        calories_burned=calories_burned,
    )
    session.add(workout_session)

    # Update UserStats
    stats = session.exec(select(UserStats).where(UserStats.user_id == current_user.id)).first()
    if not stats:
        stats = UserStats(user_id=current_user.id)
        session.add(stats)

    from models import Exercise
    from sqlalchemy import func
    import uuid

    for ex in payload.exercises:
        name_clean = ex.exercise_name.lower().replace('-', ' ').strip()
        total_reps = ex.sets_completed * ex.reps_completed
        if 'push' in name_clean:
            stats.totalPushUps += total_reps
        elif 'sit' in name_clean:
            stats.totalSitUps += total_reps
            
        # Create ExerciseLog for this exercise
        db_exercise = session.exec(
            select(Exercise).where(
                (func.replace(func.lower(Exercise.name), '-', ' ') == name_clean) |
                (func.replace(Exercise.slug, '-', ' ') == name_clean)
            )
        ).first()
        exercise_id = db_exercise.id if db_exercise else uuid.UUID("00000000-0000-0000-0000-000000000000")
        
        exercise_log = ExerciseLog(
            session_id=workout_session.id,
            exercise_id=exercise_id,
            set_number=ex.sets_completed,
            reps_completed=ex.reps_completed,
            duration_seconds=ex.duration_seconds,
            is_manual_input=False,
            form_mistakes=ex.form_mistakes,
        )
        session.add(exercise_log)

    # Streak logic
    yesterday = today - timedelta(days=1)
    if stats.lastActiveDate == today:
        pass  # Already logged today
    elif stats.lastActiveDate == yesterday:
        stats.currentStreak += 1
    else:
        stats.currentStreak = 1

    if stats.currentStreak > stats.longestStreak:
        stats.longestStreak = stats.currentStreak
    stats.lastActiveDate = today
    stats.updatedAt = datetime.now(timezone.utc)

    # DailyLog upsert
    daily = session.exec(
        select(DailyLog).where(
            DailyLog.user_id == current_user.id,
            DailyLog.date == today,
        )
    ).first()
    if not daily:
        session.add(DailyLog(user_id=current_user.id, date=today, day_type="workout_completed"))

    session.commit()
    # Update weekly insights asynchronously
    background_tasks.add_task(_generate_and_save_insight, current_user.id)
    
    return {"message": "Workout logged", "current_streak": stats.currentStreak, "calories_burned": round(calories_burned, 1)}


@router.get("/me/workout-chart")
def get_workout_chart(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    from sqlalchemy import func
    from datetime import date, timedelta
    from models import Exercise, ExerciseLog
    
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)
    
    # 1. Overall Daily Time (Last 30 Days)
    daily_overall = session.exec(
        select(WorkoutSession.date, func.sum(WorkoutSession.duration_seconds))
        .where(WorkoutSession.user_id == current_user.id, WorkoutSession.date >= thirty_days_ago)
        .group_by(WorkoutSession.date)
        .order_by(WorkoutSession.date)
    ).all()
    
    overall_30 = [{"date": d.isoformat(), "duration_seconds": s} for d, s in daily_overall]
    overall_7 = [item for item in overall_30 if date.fromisoformat(item["date"]) >= seven_days_ago]
    
    # 2. Exercise Specific Pace/Time & Form Mistakes
    daily_exercises_raw = session.exec(
        select(WorkoutSession.date, Exercise.name, ExerciseLog.duration_seconds, ExerciseLog.reps_completed, ExerciseLog.form_mistakes)
        .join(ExerciseLog, WorkoutSession.id == ExerciseLog.session_id)
        .join(Exercise, ExerciseLog.exercise_id == Exercise.id)
        .where(WorkoutSession.user_id == current_user.id, WorkoutSession.date >= thirty_days_ago)
    ).all()
    
    grouped_exercises = {}
    for d, name, dur, reps, mistakes in daily_exercises_raw:
        key = (d, name)
        if key not in grouped_exercises:
            grouped_exercises[key] = {"dur": 0, "reps": 0, "mistakes_count": 0}
        grouped_exercises[key]["dur"] += (dur or 0)
        grouped_exercises[key]["reps"] += (reps or 0)
        
        m_count = 0
        if isinstance(mistakes, dict):
            m_count = sum(mistakes.values())
        grouped_exercises[key]["mistakes_count"] += m_count

    exercises_30 = {}
    exercises_7 = {}
    
    # Sort keys by date to maintain chronological order
    for key in sorted(grouped_exercises.keys(), key=lambda k: k[0]):
        d, name = key
        data = grouped_exercises[key]
        
        item = {
            "date": d.isoformat(),
            "duration_seconds": data["dur"],
            "reps": data["reps"],
            "mistakes_count": data["mistakes_count"]
        }
        
        if name not in exercises_30:
            exercises_30[name] = []
            exercises_7[name] = []
            
        exercises_30[name].append(item)
        if d >= seven_days_ago:
            exercises_7[name].append(item)
            
    return {
        "monthly": {
            "overall": overall_30,
            "exercises": exercises_30
        },
        "weekly": {
            "overall": overall_7,
            "exercises": exercises_7
        }
    }


@router.get("/", response_model=List[User])
def read_users(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(select(User)).all()


@router.get("/{user_id}", response_model=User)
def read_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if str(current_user.id) != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to access this user")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=User)
def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if str(current_user.id) != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to update this user")

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    if "is_admin" in update_data and not current_user.is_admin:
        del update_data["is_admin"]

    if "password" in update_data:
        update_data["password"] = get_password_hash(update_data["password"])

    for key, value in update_data.items():
        setattr(db_user, key, value)

    db_user.updatedAt = datetime.now(timezone.utc)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


@router.post("/{user_id}/avatar", response_model=User)
async def upload_avatar(
    user_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to update this user's avatar")
        
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    public_url = await upload_image_to_cloudinary(file, folder="smafit/avatars")
    
    db_user.photoUrl = public_url
    db_user.updatedAt = datetime.now(timezone.utc)
    
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    
    return db_user


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if str(current_user.id) != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to delete this user")

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db_user.deletedAt = datetime.now(timezone.utc)
    db_user.updatedAt = datetime.now(timezone.utc)
    session.add(db_user)
    session.commit()
    return {"message": "User deleted successfully"}


@router.get("/me/dashboard-report", response_model=DashboardReportResponse)
def get_dashboard_report(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    stats = session.exec(select(UserStats).where(UserStats.user_id == current_user.id)).first()
    profile = session.exec(select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)).first()
    
    # 1. Weekly activity (last 7 days)
    today = date.today()
    weekly_activity = []
    max_duration = 3600 # 1 hour = 1.0 (100%)
    from datetime import timedelta
    for i in range(7):
        d = today - timedelta(days=6 - i)
        w_sessions = session.exec(select(WorkoutSession).where(WorkoutSession.user_id == current_user.id, WorkoutSession.date == d)).all()
        total_seconds = sum(s.duration_seconds for s in w_sessions)
        activity_val = min(total_seconds / max_duration, 1.0)
        weekly_activity.append(round(activity_val, 2))

    # 2. Goals Progress (Target Bulanan)
    # Konsistensi: Target 30 hari longest streak
    consistency = min((stats.longestStreak if stats else 0) / 30.0, 1.0) if stats else 0.0
    
    # Aktivitas Bulanan: Target 16 hari aktif dalam sebulan (sekitar 4x seminggu)
    start_of_month = today.replace(day=1)
    month_logs = session.exec(select(DailyLog).where(DailyLog.user_id == current_user.id, DailyLog.date >= start_of_month)).all()
    active_days_this_month = len(set(log.date for log in month_logs))
    aktivitas = min(active_days_this_month / 16.0, 1.0)
    
    goals_progress = {
        "Konsistensi (Streak Tertinggi)": round(consistency, 2),
        "Aktivitas Bulan Ini": round(aktivitas, 2)
    }

    # 3. AI Insights
    insight_data = {
        "beranda": {
            "wawasan_ai": "Selamat datang di SmaCoFit! Mulai sesi latihan pertamamu hari ini.",
            "fokus_hari_ini": ["Lakukan workout pertamamu", "Catat asupan nutrisimu"]
        },
        "laporan": {
            "wawasan_ai": "Laporan mingguanmu akan muncul setelah kamu menyelesaikan latihan dan mencatat nutrisi.",
            "fokus_hari_ini": ["Mulai rutinitas sehat", "Pantau kalori harian"]
        }
    }
    
    if stats and stats.latest_insight:
        import json
        insight_obj = stats.latest_insight
        if isinstance(insight_obj, str):
            try:
                insight_obj = json.loads(insight_obj)
            except Exception:
                insight_obj = {}

        # Check if old format
        if isinstance(insight_obj, dict) and "wawasan_ai" in insight_obj:
            insight_data["beranda"]["wawasan_ai"] = insight_obj.get("wawasan_ai", "")
            insight_data["beranda"]["fokus_hari_ini"] = insight_obj.get("fokus_hari_ini", [])
            insight_data["laporan"]["wawasan_ai"] = insight_obj.get("wawasan_ai", "")
            insight_data["laporan"]["fokus_hari_ini"] = insight_obj.get("fokus_hari_ini", [])
        elif isinstance(insight_obj, dict) and "beranda" in insight_obj:
            insight_data = insight_obj
        
    return {
        "insights": insight_data,
        "weekly_activity": weekly_activity,
        "goals_progress": goals_progress
    }

def _generate_and_save_insight(user_id: str):
    import os
    import json as json_lib
    from google import genai
    from google.genai import types
    from datetime import date, timedelta
    from sqlmodel import Session, select
    from database import engine
    from models import UserStats, UserFitnessProfile, WorkoutSession, ExerciseLog, NutritionSummary, Exercise
    from sqlalchemy import func

    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        return

    with Session(engine) as session:
        stats = session.exec(select(UserStats).where(UserStats.user_id == user_id)).first()
        profile = session.exec(select(UserFitnessProfile).where(UserFitnessProfile.user_id == user_id)).first()
        if not stats or not profile:
            return

        today = date.today()

        # Aggregate form mistakes from the last 7 days

    # Aggregate form mistakes from the last 7 days
    from models import ExerciseLog
    recent_logs = session.exec(
        select(ExerciseLog)
        .join(WorkoutSession, ExerciseLog.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.date >= today - timedelta(days=7)
        )
    ).all()

    total_mistakes = {}
    ai_recorded_sessions = 0
    for log in recent_logs:
        if log.form_mistakes is not None:
            ai_recorded_sessions += 1
            for mistake, count in log.form_mistakes.items():
                total_mistakes[mistake] = total_mistakes.get(mistake, 0) + count

    mistakes_str = ""
    if ai_recorded_sessions > 0 and total_mistakes:
        # Sort and take top 3 mistakes
        top_mistakes = sorted(total_mistakes.items(), key=lambda x: x[1], reverse=True)[:3]
        mistakes_str = "Kesalahan form dominan minggu ini:\n" + "\n".join([f"- {m}: {c} kali" for m, c in top_mistakes])
    elif ai_recorded_sessions > 0 and not total_mistakes:
        mistakes_str = "Sesi latihan terekam kamera AI dan tidak ada kesalahan dominan (Form Sempurna!)."
    else:
        mistakes_str = "Catatan Sistem: Data form_mistakes (evaluasi postur) tidak terekam pada periode ini. Fokuskan analisa pada volume dan konsistensi saja."

    # Fetch Nutrition Summary for the last 7 days
    from models import NutritionSummary
    recent_nutrition = session.exec(
        select(NutritionSummary).where(
            NutritionSummary.user_id == user_id,
            NutritionSummary.date >= today - timedelta(days=7)
        )
    ).all()

    avg_kcal = 0
    avg_protein = 0
    if recent_nutrition:
        avg_kcal = sum(n.total_kcal for n in recent_nutrition) / len(recent_nutrition)
        avg_protein = sum(n.total_protein_g for n in recent_nutrition) / len(recent_nutrition)

    nutrition_str = ""
    if recent_nutrition:
        nutrition_str = f"- Rata-rata Asupan Kalori (7 hari): {avg_kcal:.1f} kcal/hari (Target: {profile.target_daily_kcal:.1f} kcal)\n"
        nutrition_str += f"            - Rata-rata Protein (7 hari): {avg_protein:.1f} g/hari"
    else:
        nutrition_str = "- Data Asupan Nutrisi: Belum ada data nutrisi tercatat minggu ini."

    onboarding_str = f"- Umur: {profile.age} tahun, Berat: {profile.weight} kg, Tinggi: {profile.height} cm\n"
    onboarding_str += f"            - Tingkat Pengalaman: {profile.skillLevel.value}, Intensitas: {profile.intensity.value}\n"
    onboarding_str += f"            - BMR: {profile.bmr:.1f} kcal, TDEE: {profile.tdee:.1f} kcal"

    # Aggregate exercise volume for the last 7 days
    from models import Exercise
    from sqlalchemy import func
    
    weekly_exercise_totals = session.exec(
        select(Exercise.name, func.sum(ExerciseLog.reps_completed))
        .join(ExerciseLog, Exercise.id == ExerciseLog.exercise_id)
        .join(WorkoutSession, ExerciseLog.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.date >= today - timedelta(days=7)
        )
        .group_by(Exercise.name)
    ).all()

    exercise_totals_str = ""
    if weekly_exercise_totals:
        exercise_totals_str = "\n".join([f"            - Total {name}: {total} repetisi/detik" for name, total in weekly_exercise_totals])
    else:
        exercise_totals_str = "            - Belum ada sesi latihan tercatat minggu ini."

    if GOOGLE_API_KEY and profile and stats:
        try:
            genai_client = genai.Client(api_key=GOOGLE_API_KEY)
            prompt = f"""
            Kamu adalah AI Personal Trainer sekaligus Pengawas Nutrisi SmaCoFit. Berikan ringkasan laporan progress mingguan untuk user berdasarkan data berikut:
            
            [PROFIL FISIK & TARGET]
            - Goal Utama User: {profile.goal.value}
            {onboarding_str}
            
            [PERFORMA LATIHAN MINGGU INI]
            - Streak Latihan Saat Ini: {stats.currentStreak} hari
            {exercise_totals_str}
            
            {mistakes_str}
            
            [ASUPAN NUTRISI MINGGU INI]
            {nutrition_str}
            
            Sebagai trainer dan pengawas nutrisi, berikan feedback yang spesifik, memotivasi, dan arahkan user dengan tepat ke goal mereka.
            - Jika asupan kalori/protein terlalu jauh dari target TDEE (berlebih atau kurang), berikan saran pola makan yang sesuai goal.
            - Jika ada catatan tentang kesalahan form, berikan saran perbaikan postur agar terhindar dari cedera.
            
            Berikan output HANYA dalam format JSON valid dengan struktur bersarang (nested) berikut:
            {{
              "beranda": {{
                "wawasan_ai": "Pesan singkat 1 kalimat untuk reminder (contoh: Sarapan belum dilog, ayo capai target proteinmu!).",
                "fokus_hari_ini": ["Max 2 poin aksi sangat singkat"]
              }},
              "laporan": {{
                "wawasan_ai": "Kesimpulan ringkas 2-3 kalimat merangkum progres mingguan secara keseluruhan.",
                "fokus_hari_ini": ["Max 3 poin fokus perbaikan"]
              }}
            }}
            """
            
            response = genai_client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                )
            )
            ai_data = json_lib.loads(response.text)
            
            stats.latest_insight = ai_data
            stats.updatedAt = datetime.now(timezone.utc)
            session.add(stats)
            session.commit()
        except Exception as e:
            print("Error generating AI insight:", e)
