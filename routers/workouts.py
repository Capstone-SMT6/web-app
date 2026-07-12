from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select
from database import get_session
from models import WorkoutSession, ExerciseLog, DailyLog, UserStats, UserFitnessProfile, DayTypeEnum
from routers.users import get_current_user, User
from services.plan_generator import generate_plan, get_active_plan

router = APIRouter(prefix="/api/workouts", tags=["workouts"])


# ─────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────

class ExerciseLogInput(BaseModel):
    exercise_name: str   # nama latihan (free text untuk sekarang)
    set_number: int
    reps_completed: int
    form_mistakes: Optional[dict] = None

class StartWorkoutRequest(BaseModel):
    duration_seconds: int = 0
    logs: List[ExerciseLogInput] = []


# ─────────────────────────────────────────
# Helpers — streak logic
# ─────────────────────────────────────────

def _recalculate_streak(user_id: str, session: Session) -> None:
    """
    Hitung ulang currentStreak berdasarkan DailyLog.
    Streak bertambah jika hari ini atau kemarin sudah ada workout_completed.
    """
    stats = session.exec(select(UserStats).where(UserStats.user_id == user_id)).first()
    if not stats:
        return

    today = date.today()

    # Ambil semua hari latihan, urutkan descending
    logs = session.exec(
        select(DailyLog)
        .where(DailyLog.user_id == user_id)
        .where(DailyLog.day_type == DayTypeEnum.workout_completed)
        .order_by(DailyLog.date.desc())
    ).all()

    if not logs:
        stats.currentStreak = 0
        stats.lastActiveDate = None
    else:
        streak = 0
        expected = today
        for log in logs:
            if log.date == expected:
                streak += 1
                expected = expected - timedelta(days=1)
            elif log.date == expected - timedelta(days=1):
                # Boleh mundur 1 hari (toleransi zona waktu)
                streak += 1
                expected = log.date - timedelta(days=1)
            else:
                break

        stats.currentStreak = streak
        stats.lastActiveDate = logs[0].date

        if streak > stats.longestStreak:
            stats.longestStreak = streak

    stats.updatedAt = datetime.now(timezone.utc)
    session.add(stats)
    session.commit()


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────

@router.post("/sessions", status_code=201)
def start_workout_session(
    body: StartWorkoutRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Simpan sesi latihan + log reps, lalu update DailyLog & streak.
    """
    today = date.today()

    # Calculate calories burned
    profile = session.exec(select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)).first()
    weight_kg = profile.weight if profile else 65.0
    duration_hours = body.duration_seconds / 3600.0
    calories_burned = 5.0 * weight_kg * duration_hours

    # 1. Buat WorkoutSession
    workout_session = WorkoutSession(
        user_id=current_user.id,
        date=today,
        duration_seconds=body.duration_seconds,
        calories_burned=calories_burned,
    )
    session.add(workout_session)
    session.flush()  # dapatkan ID

    # 2. Simpan ExerciseLog (reps per set)
    from models import Exercise
    from sqlalchemy import func
    import uuid

    total_reps = 0
    for log in body.logs:
        name_clean = log.exercise_name.lower().replace('-', ' ').strip()
        
        # Look up exercise in DB
        exercise = session.exec(
            select(Exercise).where(
                (func.lower(Exercise.name) == name_clean) |
                (Exercise.slug == log.exercise_name.lower())
            )
        ).first()
        
        exercise_id = exercise.id if exercise else uuid.UUID("00000000-0000-0000-0000-000000000000")

        exercise_log = ExerciseLog(
            session_id=workout_session.id,
            exercise_id=exercise_id,
            set_number=log.set_number,
            reps_completed=log.reps_completed,
            is_manual_input=True,
            form_mistakes=log.form_mistakes,
        )
        session.add(exercise_log)
        total_reps += log.reps_completed


    # 4. Tandai hari ini sebagai workout_completed di DailyLog (UPSERT-style)
    existing_daily = session.exec(
        select(DailyLog)
        .where(DailyLog.user_id == current_user.id)
        .where(DailyLog.date == today)
    ).first()

    if not existing_daily:
        daily_log = DailyLog(
            user_id=current_user.id,
            date=today,
            day_type=DayTypeEnum.workout_completed,
        )
        session.add(daily_log)
    else:
        existing_daily.day_type = DayTypeEnum.workout_completed
        session.add(existing_daily)

    session.commit()

    # 5. Hitung ulang streak setelah commit
    _recalculate_streak(current_user.id, session)

    return {
        "message": "Workout session saved!",
        "session_id": workout_session.id,
        "total_reps": total_reps,
        "streak": stats.currentStreak if stats else 0,
        "calories_burned": round(calories_burned, 1),
    }


@router.get("/sessions", status_code=200)
def get_my_sessions(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Ambil semua sesi latihan user (untuk kalender)."""
    sessions = session.exec(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .order_by(WorkoutSession.date.desc())
    ).all()
    return sessions


# ─────────────────────────────────────────
# Plan generation endpoints
# ─────────────────────────────────────────

class GeneratePlanRequest(BaseModel):
    fitness_profile_id: str | None = None  # if None, uses user's existing profile
    selected_days: list[str] | None = None


@router.post("/generate-plan", status_code=201)
def generate_training_plan(
    body: GeneratePlanRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Generate a new weekly training plan based on the user's fitness profile."""
    if body.fitness_profile_id:
        profile = session.get(UserFitnessProfile, body.fitness_profile_id)
        if not profile or profile.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Fitness profile not found")
    else:
        profile = session.exec(
            select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)
        ).first()
        if not profile:
            raise HTTPException(status_code=404, detail="No fitness profile found. Complete onboarding first.")

    plan = generate_plan(profile, session, selected_days=body.selected_days)
    return get_active_plan(current_user.id, session)


@router.get("/active-plan")
def get_current_plan(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get the user's currently active training plan with all days and exercises."""
    result = get_active_plan(current_user.id, session)
    if not result:
        raise HTTPException(status_code=404, detail="No active plan found. Generate a plan first.")
    return result


# ─────────────────────────────────────────
# Analytics endpoints
# ─────────────────────────────────────────

@router.get("/analytics/summary")
def analytics_summary(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Summary analytics: total workouts, total reps, streak, avg duration, favorite exercises."""
    workouts = session.exec(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .order_by(WorkoutSession.date.desc())
    ).all()

    profile = session.exec(select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)).first()
    weight_kg = profile.weight if profile else 65.0

    stats = session.exec(select(UserStats).where(UserStats.user_id == current_user.id)).first()

    total_workouts = len(workouts)
    total_duration = sum(w.duration_seconds for w in workouts)
    total_calories = sum(w.calories_burned for w in workouts)
    avg_duration = round(total_duration / total_workouts) if total_workouts > 0 else 0

    # Count reps from exercise logs
    all_session_ids = [w.id for w in workouts]
    total_reps = 0
    total_mistakes = {}
    exercise_breakdown: dict[str, dict] = {}
    
    if all_session_ids:
        from models import Exercise
        logs_with_exercise = session.exec(
            select(ExerciseLog, Exercise)
            .join(Exercise, ExerciseLog.exercise_id == Exercise.id)
            .where(ExerciseLog.session_id.in_(all_session_ids))
        ).all()
        
        for log, ex in logs_with_exercise:
            total_reps += log.reps_completed
            name = ex.name
            if name not in exercise_breakdown:
                exercise_breakdown[name] = {"reps": 0, "duration": 0, "calories": 0.0}
            
            exercise_breakdown[name]["reps"] += log.reps_completed
            exercise_breakdown[name]["duration"] += log.duration_seconds
            
            if log.form_mistakes:
                for mistake, count in log.form_mistakes.items():
                    total_mistakes[mistake] = total_mistakes.get(mistake, 0) + count

    # Calculate calories per exercise
    for name, data in exercise_breakdown.items():
        # Calories formula used in backend: 5.0 * weight_kg * duration_hours
        data["calories"] = 5.0 * weight_kg * (data["duration"] / 3600.0)

    # Convert breakdown to list
    exercise_breakdown_list = [
        {"name": k, "reps": v["reps"], "duration": v["duration"], "calories": v["calories"]}
        for k, v in exercise_breakdown.items()
    ]

    import os
    import json as json_lib
    from google import genai
    from google.genai import types

    ai_insight = {
        "score": 100.0,
        "grade": "A+",
        "message": "Kamu belum merekam latihan dengan AI. Gunakan kamera SmaCoFit untuk mendapatkan analisa otomatis form postur tubuhmu."
    }
    
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if GOOGLE_API_KEY and total_mistakes:
        try:
            genai_client = genai.Client(api_key=GOOGLE_API_KEY)
            top_mistakes = sorted(total_mistakes.items(), key=lambda x: x[1], reverse=True)[:5]
            mistakes_str = "\n".join([f"- {m}: {c} kali" for m, c in top_mistakes])
            
            prompt = f"""
            Kamu adalah pelatih kebugaran. Evaluasi performa latihan user ini berdasarkan akumulasi data kesalahan form yang terdeteksi sensor SmaCoFit:
            
            KESALAHAN FORM POSTUR:
            {mistakes_str}
            
            Nilai total skor (0-100) dan berikan Grade (A, B, C, D). 100 berarti tidak ada salah. Semakin banyak kesalahan, kurangi skornya.
            Berikan feedback singkat, 1-2 kalimat untuk memperbaiki kesalahan tersebut.
            
            JSON format:
            "score": <angka_float>,
            "grade": "<huruf>",
            "message": "<string_pesan>"
            """
            response = genai_client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            parsed_insight = json_lib.loads(response.text)
            ai_insight["score"] = float(parsed_insight.get("score", 85.0))
            ai_insight["grade"] = parsed_insight.get("grade", "B")
            ai_insight["message"] = parsed_insight.get("message", "Sesi latihan terekam.")
        except Exception as e:
            print("Error generating workout insight:", e)
    elif all_session_ids and not total_mistakes:
        ai_insight["message"] = "Form latihanmu sangat baik! Tidak ada kesalahan postur kritis yang tercatat oleh AI."

    return {
        "total_workouts": total_workouts,
        "total_reps": total_reps,
        "total_duration_seconds": total_duration,
        "total_calories": total_calories,
        "avg_duration_seconds": avg_duration,
        "current_streak": stats.currentStreak if stats else 0,
        "longest_streak": stats.longestStreak if stats else 0,
        "exercise_breakdown": exercise_breakdown_list,
        "ai_insight": ai_insight
    }


@router.get("/analytics/weekly")
def analytics_weekly(
    weeks: int = Query(default=4, ge=1, le=52),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Weekly breakdown: workouts per week, total volume, consistency score."""
    today = date.today()
    cutoff = today - timedelta(weeks=weeks)

    workouts = session.exec(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(WorkoutSession.date >= cutoff)
        .order_by(WorkoutSession.date)
    ).all()

    # Group by ISO week
    weekly_data: dict[str, dict] = {}
    for w in workouts:
        iso = w.date.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        if week_key not in weekly_data:
            weekly_data[week_key] = {"week": week_key, "workouts": 0, "total_reps": 0, "total_duration": 0}
        weekly_data[week_key]["workouts"] += 1
        weekly_data[week_key]["total_duration"] += w.duration_seconds

    # Count reps per week
    for w in workouts:
        iso = w.date.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        logs = session.exec(
            select(ExerciseLog).where(ExerciseLog.session_id == w.id)
        ).all()
        weekly_data[week_key]["total_reps"] += sum(l.reps_completed for l in logs)

    # Consistency: ratio of active days to expected training days
    daily_logs = session.exec(
        select(DailyLog)
        .where(DailyLog.user_id == current_user.id)
        .where(DailyLog.date >= cutoff)
        .where(DailyLog.day_type == DayTypeEnum.workout_completed)
    ).all()
    total_active_days = len(set(d.date for d in daily_logs))
    total_days = (today - cutoff).days
    consistency = round(total_active_days / max(total_days, 1) * 100, 1)

    return {
        "weeks": list(weekly_data.values()),
        "consistency_pct": consistency,
        "total_active_days": total_active_days,
    }


@router.get("/analytics/calendar")
def analytics_calendar(
    year: int = Query(default=date.today().year),
    month: int = Query(default=date.today().month, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Return workout days for a given month (for calendar view)."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    daily_logs = session.exec(
        select(DailyLog)
        .where(DailyLog.user_id == current_user.id)
        .where(DailyLog.date >= start)
        .where(DailyLog.date < end)
    ).all()

    return [
        {"date": dl.date.isoformat(), "day_type": dl.day_type}
        for dl in daily_logs
    ]
